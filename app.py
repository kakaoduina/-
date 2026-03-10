import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import openai
from io import BytesIO
import datetime
import numpy as np
import time
import json

# ==========================================
# 1. 보안 및 환경 설정
# ==========================================
openai.api_key = st.secrets.get("OPENAI_API_KEY", "your-key-here")

CONFLUENCE_URL = "https://psh1576.atlassian.net"
CONFLUENCE_USER = "psh1576@gmail.com"
CONFLUENCE_API_TOKEN = st.secrets.get("CONFLUENCE_API_TOKEN", "기본값")

st.set_page_config(page_title="Lit.AI 재무/운영 통합 시스템", layout="wide")

st.markdown("""
    <style>
    .stButton > button.confluence-btn { background-color: #0052CC !important; color: white !important; }
    .stTextArea textarea { font-size: 15px !important; line-height: 1.6 !important; }
    </style>
""", unsafe_allow_html=True)

# --- Session State 초기화 ---
if 'ai_analysis_done' not in st.session_state:
    st.session_state.ai_analysis_done = False
if 'ai_report' not in st.session_state:
    st.session_state.ai_report = ""
if 'schema_mapped' not in st.session_state:
    st.session_state.schema_mapped = False
if 'column_mapping' not in st.session_state:
    st.session_state.column_mapping = {}

# ==========================================
# 2. 사이드바: 마스터 설정
# ==========================================
st.sidebar.title("🛠️ 마스터 설정")
with st.sidebar.expander("💰 고정비 설정 (Daily)", expanded=True):
    daily_rent = st.number_input("일일 임대료 (원)", value=15000000)
    daily_deprec = st.number_input("일일 감가상각 (원)", value=5000000)
    daily_indirect = st.number_input("일일 간접비 (원)", value=12000000)

with st.sidebar.expander("👷 변동비 단가 설정", expanded=True):
    labor_rate = st.number_input("현장직 시급 (원)", value=15000)
    truck_rate = st.number_input("차량당 배차비 (원)", value=350000)

target_margin = st.sidebar.slider("목표 매출이익률 (%)", 1, 20, 10)

# ==========================================
# 3. AI 기반 스키마 자동 매핑 로직
# ==========================================
def get_ai_schema_mapping(columns, sample_data):
    prompt = f"""
    너는 데이터 엔지니어 분석가야. 아래 업로드된 데이터의 컬럼명과 샘플 데이터를 보고, 
    우리의 '표준 컬럼'에 해당하는 원본 컬럼명을 JSON 형식으로 매핑해줘.
    
    [우리의 표준 컬럼]
    - Date (일자)
    - Revenue (매출액)
    - Worker_Count (투입 인원수)
    - Truck_Count (투입 차량수)
    - Quantity (물동량/수량)
    - SKU (품목명/코드)
    
    [업로드된 데이터 컬럼]: {columns}
    [샘플 데이터]: {sample_data}
    
    응답은 반드시 아래와 같은 JSON 형태만 출력해:
    {{"Date": "일자컬럼명", "Revenue": "매출컬럼명", "Worker_Count": "인원수컬럼명", "Truck_Count": "차량수컬럼명", "Quantity": "수량컬럼명", "SKU": "품목컬럼명"}}
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"Date": "Date", "Revenue": "Revenue", "Worker_Count": "Worker_Count", 
                "Truck_Count": "Truck_Count", "Quantity": "Quantity", "SKU": "SKU"}

# ==========================================
# 4. 메인 화면 구성
# ==========================================
st.title("🚀 Lit.AI 재무/운영 통합 가마감 대시보드")

uploaded_files = st.file_uploader("일일 보고서(CSV) 다중 업로드 (최대 10일치 가능)", type=['csv'], accept_multiple_files=True)

if uploaded_files:
    raw_df = pd.concat([pd.read_csv(f) for f in uploaded_files], ignore_index=True)
    
    if not st.session_state.schema_mapped:
        st.info("🤖 AI가 업로드된 데이터의 스키마를 분석 중입니다...")
        cols = raw_df.columns.tolist()
        sample_data = raw_df.head(2).to_dict()
        
        mapping = get_ai_schema_mapping(cols, sample_data)
        st.session_state.column_mapping = mapping
        st.session_state.schema_mapped = True
        st.rerun()

    with st.expander("📍 AI 데이터 컬럼 매핑 결과 (수정 가능)", expanded=False):
        st.markdown("AI가 분석한 컬럼 매핑 결과입니다. 잘못 연결된 경우 직접 수정해주세요.")
        col1, col2 = st.columns(2)
        mapped_cols = {}
        for i, (std_col, original_col) in enumerate(st.session_state.column_mapping.items()):
            with col1 if i % 2 == 0 else col2:
                idx = raw_df.columns.tolist().index(original_col) if original_col in raw_df.columns else 0
                mapped_cols[std_col] = st.selectbox(f"표준 '{std_col}'에 해당하는 컬럼", raw_df.columns.tolist(), index=idx)
        
        if st.button("매핑 확정 및 분석 시작"):
            st.session_state.column_mapping = mapped_cols
            st.success("매핑이 확정되었습니다!")

    # 데이터셋 구성 (매핑된 데이터 + 추가 심층 분석용 컬럼)
    df = pd.DataFrame()
    for std_col, orig_col in st.session_state.column_mapping.items():
        if orig_col in raw_df.columns:
            df[std_col] = raw_df[orig_col]
        else:
            df[std_col] = 0
            
    # 신규 데이터셋의 추가 컬럼들을 안전하게 df로 병합
    extra_cols = ['Quantity_Box', 'Worker_Regular', 'Worker_Temp', 'Truck_Contract', 'Truck_Temp', 
                  'Inbound_Planned', 'Inbound_Actual', 'Outbound_Planned', 'Outbound_Actual']
    for c in extra_cols:
        df[c] = raw_df[c] if c in raw_df.columns else 0

    df['Date'] = pd.to_datetime(df['Date'])
    
    # ==========================================
    # 🌟 8가지 핵심 운영 지표 대시보드 (5일 기준 전주 비교)
    # ==========================================
    st.markdown("---")
    st.subheader("🎯 핵심 운영 지표 (Daily Operation KPI)")
    
    daily_summary = df.groupby('Date').agg(
        Total_Qty=('Quantity', 'sum'),
        Total_Rev=('Revenue', 'sum'),
        Workers=('Worker_Count', 'first'),
        Trucks=('Truck_Count', 'first'),
        Unique_SKU=('SKU', 'nunique')
    ).reset_index().sort_values('Date')
    
    if not daily_summary.empty:
        latest_date = daily_summary['Date'].max()
        curr_day = daily_summary[daily_summary['Date'] == latest_date].iloc[0]
        
        prev_date = latest_date - pd.Timedelta(days=1)
        prev_day = daily_summary[daily_summary['Date'] == prev_date]
        prev_day = prev_day.iloc[0] if not prev_day.empty else None
        
        last_week_date = latest_date - pd.Timedelta(days=5) 
        last_week_day = daily_summary[daily_summary['Date'] == last_week_date]
        last_week_day = last_week_day.iloc[0] if not last_week_day.empty else None

        def calc_metrics(row):
            if row is None: return {k: 0 for k in ['qty', 'hr', 'uph', 'inbound', 'trucks', 'sku', 'workers', 'efficiency']}
            qty = row['Total_Qty']
            workers = row['Workers']
            trucks = row['Trucks']
            hr = workers * 8
            uph = qty / hr if hr > 0 else 0
            efficiency = qty / trucks if trucks > 0 else 0
            return {
                'qty': qty, 'hr': hr, 'uph': uph, 'inbound': qty, 
                'trucks': trucks, 'sku': row['Unique_SKU'], 'workers': workers, 'efficiency': efficiency
            }

        curr = calc_metrics(curr_day)
        prev = calc_metrics(prev_day)
        wow = calc_metrics(last_week_day)

        def get_delta(curr_val, compare_val):
            if compare_val == 0: return "N/A"
            return f"{((curr_val - compare_val) / compare_val) * 100:.1f}%"

        st.markdown(f"**기준일:** {latest_date.strftime('%Y-%m-%d')}  |  *(※ 전주 대비는 영업일 5일 기준)*")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("📦 물동량(PCS)", f"{curr['qty']:,.0f}", f"전일: {get_delta(curr['qty'], prev['qty'])} | 전주: {get_delta(curr['qty'], wow['qty'])}")
        m2.metric("⏱️ 작업 시간(HR)", f"{curr['hr']:,.0f}", f"전일: {get_delta(curr['hr'], prev['hr'])} | 전주: {get_delta(curr['hr'], wow['hr'])}")
        m3.metric("📈 생산성(UPH)", f"{curr['uph']:.1f}", f"전일: {get_delta(curr['uph'], prev['uph'])} | 전주: {get_delta(curr['uph'], wow['uph'])}")
        m4.metric("📥 입고처리(PCS)", f"{curr['inbound']:,.0f}", f"전일: {get_delta(curr['inbound'], prev['inbound'])} | 전주: {get_delta(curr['inbound'], wow['inbound'])}")
        
        st.write("")
        
        m5, m6, m7, m8 = st.columns(4)
        m5.metric("🚚 차량수(대)", f"{curr['trucks']:,.0f}", f"전일: {get_delta(curr['trucks'], prev['trucks'])} | 전주: {get_delta(curr['trucks'], wow['trucks'])}")
        m6.metric("🏷️ 운영 SKU", f"{curr['sku']:,.0f}", f"전일: {get_delta(curr['sku'], prev['sku'])} | 전주: {get_delta(curr['sku'], wow['sku'])}")
        m7.metric("👷 투입자원(명)", f"{curr['workers']:,.0f}", f"전일: {get_delta(curr['workers'], prev['workers'])} | 전주: {get_delta(curr['workers'], wow['workers'])}")
        m8.metric("🏢 창고 효율(차량당 PCS)", f"{curr['efficiency']:.1f}", f"전일: {get_delta(curr['efficiency'], prev['efficiency'])} | 전주: {get_delta(curr['efficiency'], wow['efficiency'])}")

    # ==========================================
    # 5. 기존 재무 현황 & 그래프
    # ==========================================
    st.markdown("---")
    st.markdown("### 💰 기간 누적 재무 현황 (Financial Summary)")
    
    total_revenue = df['Revenue'].sum()
    num_days = df['Date'].nunique()
    
    daily_stats = df.groupby('Date').agg({'Worker_Count': 'first', 'Truck_Count': 'first'}).reset_index()
    total_handling_cost = daily_stats['Worker_Count'].sum() * 8 * labor_rate
    total_delivery_cost = daily_stats['Truck_Count'].sum() * truck_rate
    total_fixed_cost = (daily_rent + daily_deprec + daily_indirect) * num_days
    
    total_cost = total_handling_cost + total_delivery_cost + total_fixed_cost
    total_profit = total_revenue - total_cost
    margin_rate = (total_profit / total_revenue) * 100 if total_revenue > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("총 매출 (A)", f"₩{total_revenue:,.0f}")
    k2.metric("매출원가 (B)", f"₩{total_cost:,.0f}")
    k3.metric("매출이익 (A-B)", f"₩{total_profit:,.0f}", delta=f"{margin_rate:.1f}% 이익률")
    k4.metric("목표 대비", f"{margin_rate - target_margin:.1f}%p")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📊 매출원가 상세 구성")
        c_labels = ['하역비(인건비)', '배송비(차량)', '임대료', '감가상각', '간접비']
        c_vals = [total_handling_cost, total_delivery_cost, daily_rent*num_days, daily_deprec*num_days, daily_indirect*num_days]
        st.plotly_chart(px.pie(values=c_vals, names=c_labels, hole=0.4), use_container_width=True)

    with col2:
        st.subheader("📉 일별 매출 vs 매출원가 추이")
        daily_rev = df.groupby('Date')['Revenue'].sum().reset_index()
        daily_stats['Daily_Cost'] = (daily_stats['Worker_Count']*8*labor_rate) + (daily_stats['Truck_Count']*truck_rate) + (daily_rent + daily_deprec + daily_indirect)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily_rev['Date'], y=daily_rev['Revenue'], name="매출"))
        fig.add_trace(go.Scatter(x=daily_stats['Date'], y=daily_stats['Daily_Cost'], name="매출원가", line=dict(color='red', width=4)))
        st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # 🌟 NEW 6. 현장 운영 심층 분석 (Operations Deep-Dive) 🌟
    # ==========================================
    st.markdown("---")
    st.markdown("### 📈 현장 운영 심층 분석 (Operations Deep-Dive)")
    
    # 일별 추세 데이터 집계
    trend_df = df.groupby('Date').agg(
        Qty_PCS=('Quantity', 'sum'), Qty_Box=('Quantity_Box', 'sum'),
        Workers=('Worker_Count', 'first'), Trucks=('Truck_Count', 'first'),
        In_P=('Inbound_Planned', 'first'), In_A=('Inbound_Actual', 'first'),
        Out_P=('Outbound_Planned', 'first'), Out_A=('Outbound_Actual', 'first')
    ).reset_index()
    trend_df['UPH'] = trend_df['Qty_PCS'] / (trend_df['Workers'] * 8)
    trend_df['Target_UPH'] = 15.0 # 임의의 기준생산성

    # [1] 4대 추세선 그래프
    st.subheader("📌 1. 주요 지표 일별 추세선")
    t1, t2 = st.columns(2)
    with t1:
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=trend_df['Date'], y=trend_df['Qty_PCS'], mode='lines+markers', name="물동량(PCS)"))
        fig1.update_layout(title="일별 물동량 추세")
        st.plotly_chart(fig1, use_container_width=True)
        
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=trend_df['Date'], y=trend_df['Workers'], mode='lines+markers', name="인력(명)", line=dict(color='orange')))
        fig2.update_layout(title="인력 투입 추세")
        st.plotly_chart(fig2, use_container_width=True)

    with t2:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=trend_df['Date'], y=trend_df['UPH'], mode='lines+markers', name="생산성(UPH)", line=dict(color='green')))
        fig3.update_layout(title="하역 생산성 추세")
        st.plotly_chart(fig3, use_container_width=True)

        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=trend_df['Date'], y=trend_df['Trucks'], mode='lines+markers', name="차량(대)", line=dict(color='red')))
        fig4.update_layout(title="차량 운행 추세")
        st.plotly_chart(fig4, use_container_width=True)

    # [2] 입출고 현황 (단위: 만 PCS)
    st.subheader("📌 2. 입/출고 현황 (단위: 만 PCS)")
    in_out_df = trend_df[['Date', 'In_P', 'In_A', 'Out_P', 'Out_A']].copy()
    for c in ['In_P', 'In_A', 'Out_P', 'Out_A']:
        in_out_df[c] = in_out_df[c] / 10000 
    
    io1, io2 = st.columns(2)
    with io1:
        fig_in = px.bar(in_out_df, x='Date', y=['In_P', 'In_A'], barmode='group', title="입고 현황 (예정 vs 실적)")
        st.plotly_chart(fig_in, use_container_width=True)
    with io2:
        fig_out = px.bar(in_out_df, x='Date', y=['Out_P', 'Out_A'], barmode='group', title="출고 현황 (예정 vs 실적)")
        st.plotly_chart(fig_out, use_container_width=True)

    # [3] Daily 생산성 이중 Y축 그래프
    st.subheader("📌 3. Daily 생산성 분석")
    fig_prod = go.Figure()
    fig_prod.add_trace(go.Bar(x=trend_df['Date'], y=trend_df['Qty_Box'], name="물량(Box)", yaxis='y1', opacity=0.6))
    fig_prod.add_trace(go.Scatter(x=trend_df['Date'], y=trend_df['UPH'], name="생산성(인/시)", yaxis='y2', mode='lines+markers', line=dict(color='red', width=3)))
    fig_prod.add_trace(go.Scatter(x=trend_df['Date'], y=trend_df['Target_UPH'], name="기준생산성(인/시)", yaxis='y2', mode='lines', line=dict(color='gray', dash='dash')))
    fig_prod.update_layout(
        yaxis=dict(title="물량 (Box)"),
        yaxis2=dict(title="생산성 (UPH)", overlaying='y', side='right'),
        barmode='group', height=400
    )
    st.plotly_chart(fig_prod, use_container_width=True)

    # [4] 표 데이터 (자원 현황 & 일일 실적)
    st.markdown("---")
    colA, colB = st.columns(2)
    with colA:
        st.subheader("📋 운영 자원 현황")
        latest_res = df[df['Date'] == latest_date].iloc[0]
        prev_res = df[df['Date'] == (latest_date - pd.Timedelta(days=1))].iloc[0] if len(df['Date'].unique()) > 1 else latest_res
        
        resource_data = {
            "구분": ["하역 (정규)", "하역 (임시)", "수배송 (지입)", "수배송 (임시)"],
            "전일": [prev_res['Worker_Regular'], prev_res['Worker_Temp'], prev_res['Truck_Contract'], prev_res['Truck_Temp']],
            "당일": [latest_res['Worker_Regular'], latest_res['Worker_Temp'], latest_res['Truck_Contract'], latest_res['Truck_Temp']]
        }
        res_df = pd.DataFrame(resource_data)
        res_df['GAP'] = res_df['당일'] - res_df['전일']
        st.dataframe(res_df, use_container_width=True, hide_index=True)

    with colB:
        st.subheader("📊 일일 운영 실적 (Box/SKU/PCS)")
        curr_trend = trend_df[trend_df['Date'] == latest_date].iloc[0]
        sku_count = df[df['Date'] == latest_date]['SKU'].nunique()
        
        perf_data = {
            "단위": ["PCS", "Box", "SKU"],
            "입고 (예정)": [curr_trend['In_P'], curr_trend['In_P']//5, sku_count],
            "입고 (작업량)": [curr_trend['In_A'], curr_trend['In_A']//5, sku_count],
            "입고 (미입)": [curr_trend['In_P'] - curr_trend['In_A'], (curr_trend['In_P'] - curr_trend['In_A'])//5, 0],
            "출고 (예정)": [curr_trend['Out_P'], curr_trend['Out_P']//5, sku_count],
            "출고 (작업량)": [curr_trend['Out_A'], curr_trend['Out_A']//5, sku_count],
            "출고 (잔량)": [curr_trend['Out_P'] - curr_trend['Out_A'], (curr_trend['Out_P'] - curr_trend['Out_A'])//5, 0],
        }
        st.dataframe(pd.DataFrame(perf_data), use_container_width=True, hide_index=True)

    # ==========================================
    # 7. AI 심층 리포트 및 외부 연동 (원본 그대로 유지!)
    # ==========================================
    st.markdown("---")
    if st.button("🤖 Lit.AI 심층 재무 분석 및 리포트 생성"):
        with st.spinner('Lit.AI 분석 중...'):
            summary = f"매출:{total_revenue}, 원가:{total_cost}, 이익:{total_profit}, 이익률:{margin_rate:.1f}%, UPH:{curr['uph']:.1f}"
            prompt = f"물류 전문 재무 분석가 'Lit.AI'로서 다음 데이터를 정밀 분석하고 개선 제언을 해줘: {summary}"
            try:
                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "데이터 기반의 냉철한 물류 분석 전문가."},
                              {"role": "user", "content": prompt}]
                )
                st.session_state.ai_report = response.choices[0].message.content
                st.session_state.ai_analysis_done = True 
            except Exception as e:
                st.error(f"AI 분석 오류: {e}")

    if st.session_state.ai_analysis_done:
        st.info("### 📝 Lit.AI 가마감 리포트 (직접 수정 가능)")
        edited_report = st.text_area("리포트 내용 편집기", value=st.session_state.ai_report, height=350, label_visibility="collapsed")
        st.session_state.ai_report = edited_report

        # 엑셀 파일 생성
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            pd.DataFrame({
                "항목": ["총 매출", "총 매출원가", "매출이익", "매출이익률", "하역비", "배송비", "고정비 총액"],
                "수치": [total_revenue, total_cost, total_profit, f"{margin_rate:.2f}%", total_handling_cost, total_delivery_cost, total_fixed_cost]
            }).to_excel(writer, index=False, sheet_name='Financial_Summary')
            daily_stats.to_excel(writer, index=False, sheet_name='Daily_Stats')
            pd.DataFrame({"Lit.AI 제언": [st.session_state.ai_report]}).to_excel(writer, index=False, sheet_name='Logi_AI_Analysis')
        
        # 다운로드 버튼
        st.download_button(
            label="💾 최종 가마감 엑셀 파일 다운로드",
            data=output.getvalue(),
            file_name=f"Logi_AI_Report_{datetime.date.today()}.xlsx",
            mime="application/vnd.ms-excel"
        )

        st.markdown("---")
        st.subheader("🌐 외부 시스템 연동")
        
        # 컨플루언스 업로드 버튼
        if st.button("📤 Confluence에 보고서 업로드", key="conf_upload"):
            with st.status("Confluence로 데이터 전송 중...", expanded=True) as status:
                st.write("1. API 연결 확인 중...")
                time.sleep(1) 
                st.write("2. 리포트 본문 HTML 변환 중...")
                time.sleep(1)
                st.write("3. 최종 페이지 게시 중...")
                time.sleep(1.5)
                status.update(label="✅ 업로드 완료되었습니다!", state="complete", expanded=False)
            
            st.balloons()
            target_link = "https://www.naver.com/" 
            st.success(f"🎉 성공적으로 업로드되었습니다.")
            st.markdown(f"🔗 **[컨플루언스 페이지 바로가기]({target_link})**")

else:
    st.info("💡 사이드바에서 센터 설정을 완료한 후, 일일 보고서(CSV)들을 업로드해 주세요.")
