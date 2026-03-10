import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import openai
from io import BytesIO
import datetime
import numpy as np
import time

# ==========================================
# 1. 보안 및 환경 설정
# ==========================================
# 스트림릿 Secrets에서 API 키를 가져옵니다.
openai.api_key = st.secrets.get("OPENAI_API_KEY", "your-key-here")

# 컨플루언스 설정
CONFLUENCE_URL = "https://psh1576.atlassian.net"
CONFLUENCE_USER = "psh1576@gmail.com"
CONFLUENCE_API_TOKEN = st.secrets.get("CONFLUENCE_API_TOKEN", "기본값")

st.set_page_config(page_title="Lit.AI 재무/운영 통합 시스템", layout="wide")

# CSS 스타일 정의 (컨플루언스 스타일 버튼 포함)
st.markdown("""
    <style>
    /* 컨플루언스 브랜드 컬러 버튼 스타일 */
    .stButton > button.confluence-btn {
        background-color: #0052CC !important;
        color: white !important;
        border-radius: 3px !important;
        padding: 0.6rem 1.2rem !important;
        border: none !important;
        font-weight: 500 !important;
        transition: background-color 0.2s ease !important;
    }
    .stButton > button.confluence-btn:hover {
        background-color: #0747A6 !important;
        color: white !important;
    }
    .stButton > button.confluence-btn:active {
        background-color: #091E42 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 사이드바: 마스터 설정
# ==========================================
st.sidebar.title("🛠️ 마스터 설정")
st.sidebar.info("센터 운영 상황에 맞는 고정비와 단가를 입력하세요.")

with st.sidebar.expander("💰 고정비 설정 (Daily)", expanded=True):
    daily_rent = st.number_input("일일 임대료 (원)", value=15000000)
    daily_deprec = st.number_input("일일 감가상각 (원)", value=5000000)
    daily_indirect = st.number_input("일일 간접비 (원)", value=12000000)

with st.sidebar.expander("👷 변동비 단가 설정", expanded=True):
    labor_rate = st.number_input("현장직 시급 (원)", value=15000)
    truck_rate = st.number_input("차량당 배차비 (원)", value=350000)

st.sidebar.markdown("---")
target_margin = st.sidebar.slider("목표 매출이익률 (%)", 1, 20, 10)

# ==========================================
# 3. 분석 로직 함수
# ==========================================
def get_logi_ai_analysis(summary):
    prompt = f"물류 전문 재무 분석가 'Lit.AI'로서 다음 데이터를 정밀 분석하고 개선 제언을 해줘: {summary}"
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "데이터 기반의 냉철한 물류 분석 전문가."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 분석 오류: {e}"

# ==========================================
# 4. 메인 화면 구성
# ==========================================
st.title("🚀 Lit.AI 재무/운영 통합 가마감 대시보드")
st.markdown("매출, 매출원가, **매출이익**을 실시간으로 분석하여 가마감을 수행합니다.")

uploaded_files = st.file_uploader("5일치 보고서(CSV) 업로드", type=['csv'], accept_multiple_files=True)

if uploaded_files:
    # 데이터 통합
    df = pd.concat([pd.read_csv(f) for f in uploaded_files], ignore_index=True)
    
    # --- 재무 및 운영 지표 계산 ---
    total_revenue = df['Revenue'].sum()
    unique_days = df['Date'].unique()
    num_days = len(unique_days)
    
    daily_stats = df.groupby('Date').agg({'Worker_Count': 'first', 'Truck_Count': 'first'}).reset_index()
    
    # 1. 매출원가 (COGS) 계산
    total_handling_cost = daily_stats['Worker_Count'].sum() * 8 * labor_rate
    total_delivery_cost = daily_stats['Truck_Count'].sum() * truck_rate
    total_fixed_cost = (daily_rent + daily_deprec + daily_indirect) * num_days
    
    total_cost = total_handling_cost + total_delivery_cost + total_fixed_cost
    
    # 2. 매출이익 (Gross Profit) 계산
    total_profit = total_revenue - total_cost
    margin_rate = (total_profit / total_revenue) * 100 if total_revenue > 0 else 0

    # --- 상단 핵심 지표 ---
    st.markdown("### 💰 주간 재무 현황 (Financial Summary)")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("총 매출 (A)", f"₩{total_revenue:,.0f}")
    k2.metric("매출원가 (B)", f"₩{total_cost:,.0f}", help="하역비 + 배송비 + 고정비 합계")
    k3.metric("매출이익 (A-B)", f"₩{total_profit:,.0f}", delta=f"{margin_rate:.1f}% 이익률")
    k4.metric("목표 대비", f"{margin_rate - target_margin:.1f}%p", delta_color="normal")

    # --- 시각화 ---
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📊 매출원가 상세 구성")
        c_labels = ['하역비(인건비)', '배송비(차량)', '임대료', '감가상각', '간접비']
        c_vals = [total_handling_cost, total_delivery_cost, daily_rent*num_days, daily_deprec*num_days, daily_indirect*num_days]
        st.plotly_chart(px.pie(values=c_vals, names=c_labels, hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel), use_container_width=True)

    with col2:
        st.subheader("📉 일별 매출 vs 매출원가 추이")
        daily_rev = df.groupby('Date')['Revenue'].sum().reset_index()
        daily_stats['Daily_Cost'] = (daily_stats['Worker_Count']*8*labor_rate) + (daily_stats['Truck_Count']*truck_rate) + (daily_rent + daily_deprec + daily_indirect)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily_rev['Date'], y=daily_rev['Revenue'], name="매출"))
        fig.add_trace(go.Scatter(x=daily_stats['Date'], y=daily_stats['Daily_Cost'], name="매출원가", line=dict(color='red', width=4)))
        st.plotly_chart(fig, use_container_width=True)

    # --- 현장 실무 분석 ---
    st.markdown("---")
    st.subheader("❓ 현장 실무 분석 (Field Practical Insights)")
    q1, q2, q3 = st.columns(3)
    
    total_qty = df['Quantity'].sum()
    total_man_hours = daily_stats['Worker_Count'].sum() * 8
    
    if q1.button("👷 생산성(UPH) 분석"):
        uph = total_qty / total_man_hours
        st.success(f"평균 **UPH는 {uph:.2f}**입니다. (목표 15.0 대비 {'양호' if uph > 15 else '점검 필요'})")
    
    if q2.button("🚚 차량당 적재 효율"):
        eff = total_qty / daily_stats['Truck_Count'].sum()
        st.warning(f"차량 1대당 평균 **{eff:.1f}개** 처리")

    if q3.button("💸 최대 원가 비중 확인"):
        max_idx = np.argmax(c_vals)
        st.error(f"최대 원가 항목: **'{c_labels[max_idx]}'**")

    # --- AI 분석 및 리포트 다운로드 ---
    st.markdown("---")
    if st.button("🤖 Lit.AI 심층 재무 분석 및 리포트 생성"):
        with st.spinner('Lit.AI 분석 중...'):
            summary = f"매출:{total_revenue}, 원가:{total_cost}, 이익:{total_profit}, 이익률:{margin_rate:.1f}%"
            report = get_logi_ai_analysis(summary)
            
            st.info("### 🤖 Lit.AI 가마감 리포트")
            st.write(report)

            # 엑셀 파일 생성
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                pd.DataFrame({
                    "항목": ["총 매출", "총 매출원가", "매출이익", "매출이익률", "하역비", "배송비", "고정비 총액"],
                    "수치": [total_revenue, total_cost, total_profit, f"{margin_rate:.2f}%", total_handling_cost, total_delivery_cost, total_fixed_cost]
                }).to_excel(writer, index=False, sheet_name='Financial_Summary')
                daily_stats.to_excel(writer, index=False, sheet_name='Daily_Stats')
                pd.DataFrame({"Lit.AI 제언": [report]}).to_excel(writer, index=False, sheet_name='Logi_AI_Analysis')
            
            # 다운로드 버튼
            st.download_button(
                label="💾 최종 가마감 엑셀 파일 다운로드",
                data=output.getvalue(),
                file_name=f"Logi_AI_Report_{datetime.date.today()}.xlsx",
                mime="application/vnd.ms-excel"
            )

            # ---------------------------------------------------------
            # [신규] 컨플루언스 업로드 섹션
            # ---------------------------------------------------------
            st.markdown("---")
            st.subheader("🌐 외부 시스템 연동")
            
            if st.button("📤 Confluence에 보고서 업로드", key="conf_upload", help="아틀라시안 컨플루언스로 데이터를 전송합니다."):
                # 버튼 클래스를 CSS로 제어하기 위해 key를 지정했습니다.
                # 진행 상태 시뮬레이션
                with st.status("Confluence API 연결 및 데이터 전송 중...", expanded=True) as status:
                    st.write("Confluence 스페이스 권한 확인 중...")
                    time.sleep(1.5)
                    st.write("가마감 데이터 HTML 변환 중...")
                    time.sleep(1.5)
                    st.write("차트 이미지 업로드 및 페이지 생성 중...")
                    time.sleep(2)
                    status.update(label="✅ 업로드 완료!", state="complete", expanded=False)
                
                st.balloons()
                st.success("✨ 업로드가 완료되었습니다!")
                
                # 수정 가능한 타겟 링크
                target_url = "https://www.naver.com/" 
                st.markdown(f"🔗 **[컨플루언스에서 생성된 페이지 확인하기]({target_url})**")

else:
    st.info("💡 사이드바에서 센터 설정을 완료한 후, 일일 보고서(CSV)들을 업로드해 주세요.")
