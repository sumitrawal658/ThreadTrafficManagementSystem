"""
Monitoring dashboard for the Threads Traffic Management System.
"""

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import time
import os
import sys
import asyncio
from datetime import datetime, timedelta
import threading
import json
from pathlib import Path

# Add parent directory to path so we can import modules
sys.path.insert(0, str(Path(__file__).resolve().parent))

from database.models import DatabaseManager, SystemMetric, BotAccount, TrendingPost, ReplyActivity, FollowActivity
from orchestration.scheduler import Scheduler
from config.settings import DASHBOARD, MAX_FOLLOWS_PER_DAY, MAX_REPLIES_PER_DAY, SCRAPE_INTERVAL_MINUTES


# Initialize database manager
db_manager = DatabaseManager()
system_metric_model = SystemMetric(db_manager)
bot_account_model = BotAccount(db_manager)
trending_post_model = TrendingPost(db_manager)
reply_activity_model = ReplyActivity(db_manager)
follow_activity_model = FollowActivity(db_manager)

# Initialize scheduler
scheduler = Scheduler(db_manager, headless=True)

# Set page config
st.set_page_config(
    page_title="Threads Traffic Management Dashboard",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply custom CSS
st.markdown("""
<style>
    .main {
        background-color: #f5f5f5;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #4e8cff;
        color: white;
    }
    .metric-card {
        background-color: white;
        border-radius: 5px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .emergency-button {
        background-color: #ff4b4b;
        color: white;
        font-weight: bold;
        padding: 10px 20px;
        border-radius: 5px;
        border: none;
        cursor: pointer;
    }
    .success-rate-high {
        color: #0cce6b;
        font-weight: bold;
    }
    .success-rate-medium {
        color: #ffa500;
        font-weight: bold;
    }
    .success-rate-low {
        color: #ff4b4b;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("🧵 Threads Traffic")
    st.subheader("Management System")
    
    system_status = "🟢 Online" if scheduler.is_running else "🔴 Offline"
    st.markdown(f"### System Status: {system_status}")
    
    if scheduler.is_running:
        if st.button("Stop System", type="primary"):
            scheduler.stop()
            st.rerun()
    else:
        if st.button("Start System", type="primary"):
            scheduler.start()
            st.rerun()
    
    st.markdown("---")
    
    st.markdown("### Emergency Controls")
    
    if st.button("⚠️ EMERGENCY SHUTDOWN", type="primary", help="Immediately stop all bot operations"):
        scheduler.create_emergency_shutdown()
        st.warning("Emergency shutdown initiated! System will stop all operations.")
    
    st.markdown("---")
    
    # Display last update time
    st.markdown("### Dashboard Info")
    st.markdown(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
    
    # Add refresh button
    if st.button("🔄 Refresh Data"):
        st.rerun()


# Function to get metrics
def get_metrics_data():
    # Get summary data from scheduler
    summary = scheduler.get_metrics_summary()
    
    # Get daily metrics
    daily_metrics = system_metric_model.get_metrics("daily_summary", limit=7)
    
    # Get recent activities
    with db_manager as cursor:
        # Recent follows
        cursor.execute('''
        SELECT fa.*, ba.username as bot_username 
        FROM follow_activity fa
        JOIN bot_accounts ba ON fa.bot_account_id = ba.id
        ORDER BY fa.timestamp DESC
        LIMIT 10
        ''')
        recent_follows = [dict(row) for row in cursor.fetchall()]
        
        # Recent replies
        cursor.execute('''
        SELECT ra.*, ba.username as bot_username, tp.post_url, tp.author_username 
        FROM reply_activity ra
        JOIN bot_accounts ba ON ra.bot_account_id = ba.id
        JOIN trending_posts tp ON ra.post_id = tp.post_id
        ORDER BY ra.timestamp DESC
        LIMIT 10
        ''')
        recent_replies = [dict(row) for row in cursor.fetchall()]
        
        # Bot accounts with stats
        cursor.execute('''
        SELECT 
            ba.*,
            (SELECT COUNT(*) FROM follow_activity fa WHERE fa.bot_account_id = ba.id AND fa.status = 'completed') as total_follows,
            (SELECT COUNT(*) FROM reply_activity ra WHERE ra.bot_account_id = ba.id AND ra.status = 'completed') as total_replies
        FROM bot_accounts ba
        ORDER BY ba.id
        ''')
        bot_accounts = [dict(row) for row in cursor.fetchall()]
        
        # Top trending posts
        cursor.execute('''
        SELECT * FROM trending_posts
        ORDER BY like_count DESC, reply_count DESC
        LIMIT 10
        ''')
        top_posts = [dict(row) for row in cursor.fetchall()]
    
    return {
        "summary": summary,
        "daily_metrics": daily_metrics,
        "recent_follows": recent_follows,
        "recent_replies": recent_replies,
        "bot_accounts": bot_accounts,
        "top_posts": top_posts
    }


# Main content
metrics_data = get_metrics_data()

# Dashboard tabs
tabs = st.tabs(["📊 Overview", "🤖 Bot Accounts", "📈 Trending Posts", "📝 Activities", "⚙️ System Logs"])

# Overview Tab
with tabs[0]:
    st.header("System Overview")
    
    # Summary metrics in cards
    summary = metrics_data["summary"]
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Active Bot Accounts", summary.get("active_accounts", 0))
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Follows Today", summary.get("follows_today", 0))
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Replies Today", summary.get("replies_today", 0))
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Posts Discovered", summary.get("posts_discovered", 0))
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Success rates
    st.subheader("Success Rates")
    
    col1, col2 = st.columns(2)
    
    with col1:
        processing_rate = summary.get("processing_rate", 0)
        rate_class = "success-rate-high" if processing_rate > 80 else "success-rate-medium" if processing_rate > 50 else "success-rate-low"
        
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(f"### Post Processing Rate")
        st.markdown(f'<p class="{rate_class}">{processing_rate:.1f}%</p>', unsafe_allow_html=True)
        st.progress(processing_rate / 100)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        # Get recent success rates for activities
        with db_manager as cursor:
            cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success
            FROM follow_activity
            WHERE timestamp >= datetime('now', '-24 hours')
            ''')
            follow_result = cursor.fetchone()
            follow_success_rate = 0
            if follow_result and follow_result[0] > 0:
                follow_success_rate = (follow_result[1] / follow_result[0]) * 100
                
            cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success
            FROM reply_activity
            WHERE timestamp >= datetime('now', '-24 hours')
            ''')
            reply_result = cursor.fetchone()
            reply_success_rate = 0
            if reply_result and reply_result[0] > 0:
                reply_success_rate = (reply_result[1] / reply_result[0]) * 100
        
        rate_class = "success-rate-high" if (follow_success_rate + reply_success_rate) / 2 > 80 else "success-rate-medium" if (follow_success_rate + reply_success_rate) / 2 > 50 else "success-rate-low"
        
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(f"### Activity Success Rates")
        st.markdown(f'<p>Follow Success: <span class="{rate_class}">{follow_success_rate:.1f}%</span></p>', unsafe_allow_html=True)
        st.markdown(f'<p>Reply Success: <span class="{rate_class}">{reply_success_rate:.1f}%</span></p>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Activity trends chart
    st.subheader("Activity Trends (Last 7 Days)")
    
    # Prepare data for chart
    daily_data = []
    for metric in metrics_data["daily_metrics"]:
        if "metadata" in metric and metric["metadata"]:
            data = {
                "date": metric["metadata"].get("date", ""),
                "follows": metric["metadata"].get("follows", 0),
                "replies": metric["metadata"].get("replies", 0),
                "posts_discovered": metric["metadata"].get("posts_discovered", 0)
            }
            daily_data.append(data)
    
    if daily_data:
        daily_df = pd.DataFrame(daily_data)
        daily_df["date"] = pd.to_datetime(daily_df["date"])
        
        # Reshape for chart
        chart_data = pd.melt(
            daily_df, 
            id_vars=["date"], 
            value_vars=["follows", "replies", "posts_discovered"],
            var_name="metric", 
            value_name="count"
        )
        
        # Create chart
        chart = alt.Chart(chart_data).mark_line(point=True).encode(
            x=alt.X('date:T', title="Date"),
            y=alt.Y('count:Q', title="Count"),
            color=alt.Color('metric:N', title="Metric"),
            tooltip=['date:T', 'metric:N', 'count:Q']
        ).properties(
            width=700,
            height=400
        ).interactive()
        
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No daily metrics data available yet")


# Bot Accounts Tab
with tabs[1]:
    st.header("Bot Accounts")
    
    # Display bot accounts
    if metrics_data["bot_accounts"]:
        # Convert to DataFrame
        accounts_df = pd.DataFrame(metrics_data["bot_accounts"])
        
        # Calculate statistics
        accounts_df["follow_ratio"] = accounts_df["total_follows"] / accounts_df["total_replies"].replace(0, 1)
        accounts_df["daily_activity"] = accounts_df["daily_follows"] + accounts_df["daily_replies"]
        accounts_df["activity_percentage"] = (accounts_df["daily_activity"] / 
                                             (accounts_df[["daily_follows", "daily_replies"]].max().max() * 2)) * 100
        
        # Display accounts table
        st.dataframe(
            accounts_df[["id", "username", "account_status", "daily_follows", "daily_replies", 
                        "total_follows", "total_replies", "last_login"]],
            use_container_width=True
        )
        
        # Display activity bar chart
        st.subheader("Account Activity Levels")
        
        activity_chart = alt.Chart(accounts_df).mark_bar().encode(
            x=alt.X('username:N', title="Bot Account"),
            y=alt.Y('daily_activity:Q', title="Daily Activity Count"),
            color=alt.Color('account_status:N', title="Status"),
            tooltip=['username', 'daily_follows', 'daily_replies', 'daily_activity']
        ).properties(
            width=700,
            height=400
        )
        
        st.altair_chart(activity_chart, use_container_width=True)
    else:
        st.info("No bot accounts configured yet")
    
    st.markdown("---")
    
    # Add account form
    with st.expander("Add New Bot Account"):
        with st.form("add_account_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            submitted = st.form_submit_button("Add Account")
            if submitted and username and password:
                try:
                    bot_account_model.add_account(username, password)
                    st.success(f"Account {username} added successfully!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding account: {str(e)}")


# Trending Posts Tab
with tabs[2]:
    st.header("Trending Posts")
    
    # Display top trending posts
    if metrics_data["top_posts"]:
        # Convert to DataFrame
        posts_df = pd.DataFrame(metrics_data["top_posts"])
        
        # Calculate engagement score
        posts_df["engagement_score"] = posts_df["like_count"] + (posts_df["reply_count"] * 2) + (posts_df["repost_count"] * 3)
        
        # Display top posts
        for i, post in enumerate(metrics_data["top_posts"][:5]):
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.markdown(f"#### {i+1}. Post by @{post['author_username']}")
            st.markdown(f"**Content:** {post['content'][:100]}..." if len(post.get('content', '')) > 100 else f"**Content:** {post.get('content', '')}")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"👍 **Likes:** {post['like_count']:,}")
            with col2:
                st.markdown(f"💬 **Replies:** {post['reply_count']:,}")
            with col3:
                st.markdown(f"🔄 **Reposts:** {post['repost_count']:,}")
                
            st.markdown(f"[View Post]({post['post_url']})")
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("")  # Add spacing
        
        # Display engagement chart
        st.subheader("Top Posts by Engagement")
        
        chart_data = posts_df.sort_values("engagement_score", ascending=False).head(10)
        
        engagement_chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('engagement_score:Q', title="Engagement Score"),
            y=alt.Y('author_username:N', title="Author", sort='-x'),
            color=alt.Color('is_processed:N', title="Processed", 
                          scale=alt.Scale(domain=[0, 1], range=['#FFA500', '#4CAF50'])),
            tooltip=['author_username', 'like_count', 'reply_count', 'repost_count', 'engagement_score']
        ).properties(
            width=700,
            height=400
        )
        
        st.altair_chart(engagement_chart, use_container_width=True)
    else:
        st.info("No trending posts discovered yet")
    
    # Manual scrape button
    if st.button("Manually Scrape New Posts"):
        st.info("Starting manual scrape...")
        
        # Run scraper in background
        def run_scrape():
            asyncio.run(scheduler._run_scraper_task())
        
        # Start thread
        thread = threading.Thread(target=run_scrape)
        thread.start()
        
        # Show spinner while waiting
        with st.spinner("Scraping posts..."):
            thread.join()
            
        st.success("Scrape completed!")
        time.sleep(1)
        st.rerun()


# Activities Tab
with tabs[3]:
    st.header("Recent Activities")
    
    # Create tabs for different activity types
    activity_tabs = st.tabs(["Follows", "Replies"])
    
    # Follows subtab
    with activity_tabs[0]:
        st.subheader("Recent Follow Activities")
        
        if metrics_data["recent_follows"]:
            # Convert to DataFrame
            follows_df = pd.DataFrame(metrics_data["recent_follows"])
            
            # Format data
            follows_df["timestamp"] = pd.to_datetime(follows_df["timestamp"])
            follows_df["timestamp"] = follows_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
            
            # Display follows table
            st.dataframe(
                follows_df[["bot_username", "target_username", "action_type", "status", "timestamp"]],
                use_container_width=True
            )
            
            # Display action type distribution
            st.subheader("Follow Action Distribution")
            
            action_counts = follows_df["action_type"].value_counts().reset_index()
            action_counts.columns = ["action_type", "count"]
            
            action_chart = alt.Chart(action_counts).mark_arc().encode(
                theta=alt.Theta(field="count", type="quantitative"),
                color=alt.Color(field="action_type", type="nominal"),
                tooltip=["action_type", "count"]
            ).properties(
                width=400,
                height=400
            )
            
            st.altair_chart(action_chart, use_container_width=True)
        else:
            st.info("No follow activities recorded yet")
    
    # Replies subtab
    with activity_tabs[1]:
        st.subheader("Recent Reply Activities")
        
        if metrics_data["recent_replies"]:
            # Convert to DataFrame
            replies_df = pd.DataFrame(metrics_data["recent_replies"])
            
            # Format data
            replies_df["timestamp"] = pd.to_datetime(replies_df["timestamp"])
            replies_df["timestamp"] = replies_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
            
            # Display replies table
            st.dataframe(
                replies_df[["bot_username", "author_username", "content", "status", "timestamp"]],
                use_container_width=True
            )
            
            # Show some example replies
            st.subheader("Sample Replies")
            
            for i, reply in enumerate(metrics_data["recent_replies"][:3]):
                if reply.get("status") == "completed":
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.markdown(f"**Bot:** {reply.get('bot_username')} → **Target:** @{reply.get('author_username')}")
                    st.markdown(f"**Reply:** {reply.get('content')}")
                    st.markdown(f"**Time:** {reply.get('timestamp')}")
                    st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown("")  # Add spacing
        else:
            st.info("No reply activities recorded yet")


# System Logs Tab
with tabs[4]:
    st.header("System Logs & Configuration")
    
    # Create log viewer
    st.subheader("System Metrics")
    
    # Get all metric types
    with db_manager as cursor:
        cursor.execute('''
        SELECT DISTINCT metric_name FROM system_metrics
        ''')
        metric_types = [row[0] for row in cursor.fetchall()]
    
    # Let user select metric type
    selected_metric = st.selectbox("Select Metric Type", metric_types if metric_types else ["No metrics available"])
    
    if metric_types:
        # Get metrics data
        metrics = system_metric_model.get_metrics(selected_metric, limit=100, hours=48)
        
        if metrics:
            # Convert to DataFrame
            metrics_df = pd.DataFrame(metrics)
            
            # Format data
            metrics_df["timestamp"] = pd.to_datetime(metrics_df["timestamp"])
            
            # Create line chart
            chart = alt.Chart(metrics_df).mark_line().encode(
                x=alt.X('timestamp:T', title="Time"),
                y=alt.Y('metric_value:Q', title="Value"),
                tooltip=['timestamp:T', 'metric_value:Q']
            ).properties(
                width=700,
                height=400
            ).interactive()
            
            st.altair_chart(chart, use_container_width=True)
            
            # Display raw data
            with st.expander("View Raw Metrics Data"):
                st.dataframe(metrics_df, use_container_width=True)
        else:
            st.info(f"No data available for metric type: {selected_metric}")
    
    st.markdown("---")
    
    # System configuration section
    st.subheader("System Configuration")
    
    # Display key system settings
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    st.markdown("#### Activity Limits")
    st.markdown(f"**Max Follows Per Day:** {MAX_FOLLOWS_PER_DAY}")
    st.markdown(f"**Max Replies Per Day:** {MAX_REPLIES_PER_DAY}")
    st.markdown(f"**Scrape Interval:** {SCRAPE_INTERVAL_MINUTES} minutes")
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Emergency shutdown option
    st.subheader("Emergency Controls")
    
    if st.button("⚠️ TRIGGER EMERGENCY SHUTDOWN", type="primary"):
        scheduler.create_emergency_shutdown()
        st.warning("Emergency shutdown initiated! System will stop all operations.")


# Auto-refresh the dashboard
if DASHBOARD.get("update_interval_seconds"):
    time.sleep(DASHBOARD["update_interval_seconds"])
    st.rerun()


if __name__ == "__main__":
    # This will be executed when running the dashboard directly
    import asyncio
    
    # Initialize database
    from database.init_db import init_database
    init_database()
    
    # Start the scheduler if not running
    if not scheduler.is_running:
        scheduler.start() 