import os
import streamlit as st
import config
from helius import HeliusClient, HeliusAPIError
from filters import apply_minimum_balance_threshold, filter_holders
from calculations import compute_retention
from scoring import compute_conviction_score

# 1. Page Configuration & Title
st.set_page_config(page_title="Solana Token Conviction Score", page_icon="💎", layout="centered")
st.title("💎 Solana Token Conviction Score")
st.markdown("Analyze a token's top holders to see how strongly they are retaining their positions.")

# 2. Handle the Helius API Key securely
# Streamlit looks for secrets in environment variables or a local secrets file
helius_key = os.environ.get("HELIUS_API_KEY") or st.secrets.get("HELIUS_API_KEY")

if not helius_key:
    st.error("Missing Helius API Key! Please set it in your environment or Streamlit Secrets.")
    st.stop()

# 3. Sidebar Configuration / Controls
st.sidebar.header("Analysis Settings")
min_pct = st.sidebar.slider(
    "Min Holder % of Supply", 
    min_value=0.0001, max_value=0.01, 
    value=config.MIN_HOLDER_PCT_OF_SUPPLY, 
    step=0.0001, format="%.4f"
)
max_wallets = st.sidebar.number_input("Max Wallets to Analyze", value=config.MAX_WALLETS_TO_ANALYZE)
use_cache = st.sidebar.checkbox("Use Local Cache", value=True)

# 4. Main User Input
mint_address = st.text_input("Enter Solana Token Mint Address:", placeholder="e.g., DezXAZ8z7PnrFcQEwFb7eHzXRHN42QHgtkVxv3hZoJJ3")

if st.button("Run Analysis", type="primary") and mint_address:
    try:
        # Initialize client
        client = HeliusClient(api_key=helius_key)
        
        with st.spinner("Fetching token metadata and holder list..."):
            metadata = client.get_token_metadata(mint_address, use_cache=use_cache)
            raw_holders = client.get_token_holders(mint_address, use_cache=use_cache)

        if not raw_holders:
            st.warning("No holders found. Is the address correct?")
            st.stop()

        # Backfill decimals if missing
        for h in raw_holders:
            if not h.decimals:
                h.decimals = metadata.decimals

        # Filter out infrastructure & small holders
        qualifying_holders = apply_minimum_balance_threshold(raw_holders, metadata, min_pct_of_supply=min_pct)
        filter_result = filter_holders(qualifying_holders, metadata)
        investor_holders = filter_result.investor_holders[:max_wallets]

        if not investor_holders:
            st.warning(f"No qualifying investor wallets found above the {min_pct * 100:.3f}% threshold.")
            st.stop()

        # Analyze Wallets with a visual progress bar
        positions = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, holder in enumerate(investor_holders):
            status_text.text(f"Analyzing wallet {i+1}/{len(investor_holders)}: {holder.owner[:6]}...")
            transfers = client.get_wallet_transfers(holder.owner, mint_address, use_cache=use_cache)
            position = compute_retention(transfers, holder.owner, holder.balance)
            positions.append(position)
            progress_bar.progress((i + 1) / len(investor_holders))
        
        status_text.empty()
        progress_bar.empty()

        # Compute Score
        result = compute_conviction_score(positions)

        # 5. Display the Results beautifully
        st.success("Analysis Complete!")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="Token Name", value=f"{metadata.name} ({metadata.symbol})")
            st.metric(label="Wallets Analyzed", value=result.wallets_analyzed)
        with col2:
            if result.wallets_analyzed < config.SCORING.min_wallets_for_score:
                st.metric(label="Conviction Score", value="N/A", help="Too few qualifying wallets")
            else:
                st.metric(label="Conviction Score", value=f"{result.score} / 100")

        # Display Retention Bands breakdown
        st.subheader("Holder Retention Breakdown")
        for band in config.RETENTION_BANDS:
            count = result.band_counts.get(band.label, 0)
            st.write(f"**{band.label}**: {count} wallet(s)")

    except HeliusAPIError as e:
        st.error(f"Helius API Error: {e}")
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")