import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import openai
from io import BytesIO
import datetime
import numpy as np

# [1. 보안 설정] 모든 비밀 키는 스트림릿 Secrets에서 가져옵니다.
# 깃허브 코드에는 절대 실제 키를 적지 마세요!
openai.api_key = st.secrets["OPENAI_API_KEY"]

# 컨플루언스 정보도 Secrets로 관리하는 것이 정석입니다.
CONFLUENCE_URL = "https://psh1576.atlassian.net"
CONFLUENCE_USER = "psh1576@gmail.com"
# 아래 코드로 변경하여 보안을 지키세요.
CONFLUENCE_API_TOKEN = st.secrets.get("CONFLUENCE_API_TOKEN", "기본값") 

st.set_page_config(page_title="Lit.AI 재무/운영 통합 시스템", layout="wide")
# ==========================================
# 1. 사이드바: 고정비 및 단가 동적 입력
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
# 2. 분석 로직 함수
# ==========================================
def get_logi_ai_analysis(summary):
    prompt = f"물류 전문 재무 분석가 'Lit.AI'로서 다음 데이터를 정밀 분석하고 개선 제언을 해줘: {summary}"
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "데이터 기반의 냉철한 물류 분석 전문가."},
                      {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 분석 오류: {e}"

# ==========================================
# 3. 메인 화면 구성
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
    
    total_cost = total_handling_cost + total_delivery_cost + total_fixed_cost # 총 매출원가
    
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
        st.subheader("📊 매출원가 상세 구성 (Cost Breakdown)")
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

    # ==========================================
    # 4. 현장 실무 분석 섹션 (Q&A)
    # ==========================================
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

    # ==========================================
    # 5. 로지 AI 분석 및 엑셀 리포트
    # ==========================================
    st.markdown("---")
    if st.button("🤖 Lit.AI 심층 재무 분석 및 엑셀 다운로드"):
        with st.spinner('Lit.AI 분석 중...'):
            summary = f"매출:{total_revenue}, 원가:{total_cost}, 이익:{total_profit}, 이익률:{margin_rate:.1f}%"
            report = get_logi_ai_analysis(summary)
            
            st.info("### 🤖 Lit.AI 가마감 리포트")
            st.write(report)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # 시트 1: 재무 결산 요약
                pd.DataFrame({
                    "항목": ["총 매출", "총 매출원가", "매출이익", "매출이익률", "하역비", "배송비", "고정비 총액"],
                    "수치": [total_revenue, total_cost, total_profit, f"{margin_rate:.2f}%", total_handling_cost, total_delivery_cost, total_fixed_cost]
                }).to_excel(writer, index=False, sheet_name='Financial_Summary')
                # 시트 2: 일자별 통계
                daily_stats.to_excel(writer, index=False, sheet_name='Daily_Stats')
                # 시트 3: AI 분석
                pd.DataFrame({"Lit.AI 제언": [report]}).to_excel(writer, index=False, sheet_name='Logi_AI_Analysis')
            
            st.download_button(
                label="💾 최종 가마감 엑셀 파일 다운로드",
                data=output.getvalue(),
                file_name=f"Logi_AI_Report_{datetime.date.today()}.xlsx",
                mime="application/vnd.ms-excel"
            )
else:
    st.info("💡 사이드바에서 센터 설정을 완료한 후, 일일 보고서(CSV)들을 업로드해 주세요.")
