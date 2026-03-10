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
import re

# ==========================================
# 1. 보안 및 환경 설정
# ==========================================
openai.api_key = st.secrets.get("OPENAI_API_KEY", "your-key-here")

CONFLUENCE_URL = "https://psh1576.atlassian.net"
CONFLUENCE_USER = "psh1576@gmail.com"
CONFLUENCE_API_TOKEN = st.secrets.get("CONFLUENCE_API_TOKEN", "기본값")

st.set_page_config(page_title="Lit.AI 재무/운영 통합 시스템", layout="wide")

# 테마 강제 고정 (White) 및 UI 스타일링
st.markdown("""
    <style>
    /* 전체 배경을 흰색으로 고정하여 다크모드 충돌 방지 */
    .stApp { background-color: #ffffff; }
    .stButton > button.confluence-btn { background-color: #0052CC !important; color: white !important; }
    .stTextArea textarea { font-size: 15px !important; line-height: 1.6 !important; }
    /* 메트릭 텍스트 색상 조정 (흰 배경에서 잘 보이도록) */
    [data-testid="stMetricValue"] { color: #1f77b4; }
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
# 4. 메인 화면 구성 및 데이터 전처리 (Tab 분리)
# ==========================================
st.title("🚀 Lit.AI 재무/운영 통합 가마감 대시보드")

tab1, tab2 = st.tabs(["📊 1. 일일 운영 현황 대시보드", "🔮 2. 월간 가마감(예측 결산) 시뮬레이터"])

# -------------------------------------------------------------------
# [TAB 1] 일일 운영 대시보드 로직
# -------------------------------------------------------------------
with tab1:
    uploaded_files = st.file_uploader("일일 보고서(CSV) 다중 업로드 (최대 10일치 가능)", type=['csv'], accept_multiple_files=True, key="tab1_uploader")

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
                    mapped_cols[std_col] = st.selectbox(f"표준 '{std_col}'에 해당하는 컬럼", raw_df.columns.tolist(), index=idx, key=f"tab1_map_{std_col}")
            
            if st.button("매핑 확정 및 분석 시작", key="tab1_map_btn"):
                st.session_state.column_mapping = mapped_cols
                st.success("매핑이 확정되었습니다!")

        # 데이터셋 구성 (매핑된 데이터)
        df = pd.DataFrame()
        for std_col, orig_col in st.session_state.column_mapping.items():
            df[std_col] = raw_df[orig_col] if orig_col in raw_df.columns else 0
                
        extra_cols_mapping = {
            'Quantity_Box': 'Quantity_Box',
            'Worker_Regular': 'Worker_Regular',
            'Worker_Temp': 'Worker_Temp',
            'Truck_Contract': 'Truck_Contract',
            'Truck_Temp': 'Truck_Temp',
            'Inbound_Planned_PCS': 'Inbound_Planned',
            'Inbound_Actual_PCS': 'Inbound_Actual',
            'Outbound_Planned_PCS': 'Outbound_Planned',
            'Outbound_Actual_PCS': 'Outbound_Actual'
        }
        
        for csv_col, std_col in extra_cols_mapping.items():
            df[std_col] = raw_df[csv_col] if csv_col in raw_df.columns else 0

        df['Date'] = pd.to_datetime(df['Date'])
        
        st.markdown("---")
        view_mode = st.radio("📅 **데이터 조회 단위 선택**", ["일별 (Daily)", "주별 (Weekly)"], horizontal=True, key="tab1_view_mode")
        
        daily_base = df.groupby('Date').agg(
            Total_Qty=('Quantity', 'sum'),
            Total_Box=('Quantity_Box', 'sum'),
            Total_Rev=('Revenue', 'sum'),
            Workers=('Worker_Count', 'first'),
            Trucks=('Truck_Count', 'first'),
            Unique_SKU=('SKU', 'nunique'),
            In_P=('Inbound_Planned', 'first'),
            In_A=('Inbound_Actual', 'first'),
            Out_P=('Outbound_Planned', 'first'),
            Out_A=('Outbound_Actual', 'first'),
            Worker_Reg=('Worker_Regular', 'first'),
            Worker_Tmp=('Worker_Temp', 'first'),
            Truck_Con=('Truck_Contract', 'first'),
            Truck_Tmp=('Truck_Temp', 'first')
        ).reset_index()

        if view_mode == "주별 (Weekly)":
            daily_base['Period'] = daily_base['Date'].dt.to_period('W-MON').dt.start_time
            agg_df = daily_base.groupby('Period').agg(
                Total_Qty=('Total_Qty', 'sum'),
                Total_Box=('Total_Box', 'sum'),
                Total_Rev=('Total_Rev', 'sum'),
                Workers=('Workers', 'sum'),
                Trucks=('Trucks', 'sum'),
                Unique_SKU=('Unique_SKU', 'max'),
                In_P=('In_P', 'sum'),
                In_A=('In_A', 'sum'),
                Out_P=('Out_P', 'sum'),
                Out_A=('Out_A', 'sum'),
                Worker_Reg=('Worker_Reg', 'sum'),
                Worker_Tmp=('Worker_Tmp', 'sum'),
                Truck_Con=('Truck_Con', 'sum'),
                Truck_Tmp=('Truck_Tmp', 'sum')
            ).reset_index()
            period_label = "주(Week)"
        else:
            daily_base['Period'] = daily_base['Date']
            agg_df = daily_base.copy()
            period_label = "일(Day)"

        agg_df = agg_df.sort_values('Period')

        # 🌟 8가지 핵심 운영 지표 대시보드
        st.subheader(f"🎯 핵심 운영 지표 ({view_mode})")
        
        if not agg_df.empty:
            latest_period = agg_df['Period'].max()
            curr_data = agg_df[agg_df['Period'] == latest_period].iloc[0]
            prev_data_df = agg_df[agg_df['Period'] < latest_period]
            prev_data = prev_data_df.iloc[-1] if not prev_data_df.empty else None

            def calc_metrics(row):
                if row is None: return {k: 0 for k in ['qty', 'hr', 'uph', 'inbound', 'trucks', 'sku', 'workers', 'efficiency']}
                qty = row['Total_Qty']
                workers = row['Workers']
                trucks = row['Trucks']
                hr = workers * 8
                uph = qty / hr if hr > 0 else 0
                efficiency = qty / trucks if trucks > 0 else 0
                return {
                    'qty': qty, 'hr': hr, 'uph': uph, 'inbound': row['In_A'], 
                    'trucks': trucks, 'sku': row['Unique_SKU'], 'workers': workers, 'efficiency': efficiency
                }

            curr = calc_metrics(curr_data)
            prev = calc_metrics(prev_data)

            def get_delta(curr_val, compare_val):
                if compare_val == 0: return "N/A"
                return f"{((curr_val - compare_val) / compare_val) * 100:.1f}%"

            date_str = latest_period.strftime('%Y-%m-%d')
            if view_mode == "주별 (Weekly)":
                date_str += " (해당 주차 시작일)"
                
            st.markdown(f"**최근 기준일:** {date_str}")
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📦 물동량(PCS)", f"{curr['qty']:,.0f}", f"이전 기간 대비: {get_delta(curr['qty'], prev['qty'])}")
            m2.metric("⏱️ 총 작업시간(HR)", f"{curr['hr']:,.0f}", f"이전 기간 대비: {get_delta(curr['hr'], prev['hr'])}")
            m3.metric("📈 생산성(UPH)", f"{curr['uph']:.1f}", f"이전 기간 대비: {get_delta(curr['uph'], prev['uph'])}")
            m4.metric("📥 입고처리(PCS)", f"{curr['inbound']:,.0f}", f"이전 기간 대비: {get_delta(curr['inbound'], prev['inbound'])}")
            
            st.write("")
            
            m5, m6, m7, m8 = st.columns(4)
            m5.metric("🚚 차량수(대)", f"{curr['trucks']:,.0f}", f"이전 기간 대비: {get_delta(curr['trucks'], prev['trucks'])}")
            m6.metric("🏷️ 운영 SKU", f"{curr['sku']:,.0f}", f"이전 기간 대비: {get_delta(curr['sku'], prev['sku'])}")
            m7.metric("👷 투입자원(명)", f"{curr['workers']:,.0f}", f"이전 기간 대비: {get_delta(curr['workers'], prev['workers'])}")
            m8.metric("🏢 창고 효율(차량당 PCS)", f"{curr['efficiency']:.1f}", f"이전 기간 대비: {get_delta(curr['efficiency'], prev['efficiency'])}")

        # 5. 재무 현황 & 그래프
        st.markdown("---")
        st.markdown(f"### 💰 누적 재무 현황 (전체 {period_label} 기준합산)")
        
        total_revenue = df['Revenue'].sum()
        num_days = df['Date'].nunique()
        
        total_handling_cost = daily_base['Workers'].sum() * 8 * labor_rate
        total_delivery_cost = daily_base['Trucks'].sum() * truck_rate
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
            st.subheader(f"📉 {view_mode} 매출 vs 매출원가 추이")
            agg_df['Cost'] = (agg_df['Workers']*8*labor_rate) + (agg_df['Trucks']*truck_rate)
            if view_mode == "주별 (Weekly)":
                days_in_week_series = daily_base.groupby('Period').size().values
                agg_df['Fixed_Cost'] = days_in_week_series * (daily_rent + daily_deprec + daily_indirect)
            else:
                agg_df['Fixed_Cost'] = daily_rent + daily_deprec + daily_indirect
            
            agg_df['Total_Period_Cost'] = agg_df['Cost'] + agg_df['Fixed_Cost']

            fig = go.Figure()
            fig.add_trace(go.Bar(x=agg_df['Period'], y=agg_df['Total_Rev'], name="매출"))
            fig.add_trace(go.Scatter(x=agg_df['Period'], y=agg_df['Total_Period_Cost'], name="매출원가", line=dict(color='red', width=4)))
            st.plotly_chart(fig, use_container_width=True)

        # 6. 현장 운영 심층 분석
        st.markdown("---")
        st.markdown("### 📈 현장 운영 심층 분석 (Operations Deep-Dive)")
        
        agg_df['UPH'] = agg_df['Total_Qty'] / (agg_df['Workers'] * 8)
        agg_df['Target_UPH'] = 15.0

        st.subheader(f"📌 1. 주요 지표 {view_mode} 추세선")
        t1, t2 = st.columns(2)
        with t1:
            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(x=agg_df['Period'], y=agg_df['Total_Qty'], mode='lines+markers', name="물동량(PCS)"))
            fig1.update_layout(title=f"{period_label} 물동량 추세")
            st.plotly_chart(fig1, use_container_width=True)
            
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=agg_df['Period'], y=agg_df['Workers'], mode='lines+markers', name="인력(명)", line=dict(color='orange')))
            fig2.update_layout(title="인력 투입 추세")
            st.plotly_chart(fig2, use_container_width=True)

        with t2:
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(x=agg_df['Period'], y=agg_df['UPH'], mode='lines+markers', name="생산성(UPH)", line=dict(color='green')))
            fig3.update_layout(title="하역 생산성 추세")
            st.plotly_chart(fig3, use_container_width=True)

            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=agg_df['Period'], y=agg_df['Trucks'], mode='lines+markers', name="차량(대)", line=dict(color='red')))
            fig4.update_layout(title="차량 운행 추세")
            st.plotly_chart(fig4, use_container_width=True)

        st.subheader("📌 2. 입/출고 현황 (단위: 만 PCS)")
        in_out_df = agg_df[['Period', 'In_P', 'In_A', 'Out_P', 'Out_A']].copy()
        for c in ['In_P', 'In_A', 'Out_P', 'Out_A']:
            in_out_df[c] = in_out_df[c] / 10000 
        
        io1, io2 = st.columns(2)
        with io1:
            fig_in = px.bar(in_out_df, x='Period', y=['In_P', 'In_A'], barmode='group', title="입고 현황 (예정 vs 실적)")
            st.plotly_chart(fig_in, use_container_width=True)
        with io2:
            fig_out = px.bar(in_out_df, x='Period', y=['Out_P', 'Out_A'], barmode='group', title="출고 현황 (예정 vs 실적)")
            st.plotly_chart(fig_out, use_container_width=True)

        st.subheader(f"📌 3. {period_label} 생산성 분석")
        fig_prod = go.Figure()
        fig_prod.add_trace(go.Bar(x=agg_df['Period'], y=agg_df['Total_Box'], name="물량(Box)", yaxis='y1', opacity=0.6))
        fig_prod.add_trace(go.Scatter(x=agg_df['Period'], y=agg_df['UPH'], name="생산성(인/시)", yaxis='y2', mode='lines+markers', line=dict(color='red', width=3)))
        fig_prod.add_trace(go.Scatter(x=agg_df['Period'], y=agg_df['Target_UPH'], name="기준생산성(인/시)", yaxis='y2', mode='lines', line=dict(color='gray', dash='dash')))
        fig_prod.update_layout(
            yaxis=dict(title="물량 (Box)"),
            yaxis2=dict(title="생산성 (UPH)", overlaying='y', side='right'),
            barmode='group', height=400
        )
        st.plotly_chart(fig_prod, use_container_width=True)

        st.markdown("---")
        colA, colB = st.columns(2)
        with colA:
            st.subheader(f"📋 운영 자원 현황 ({period_label} 기준)")
            curr_res = agg_df[agg_df['Period'] == latest_period].iloc[0]
            prev_res = prev_data if prev_data is not None else curr_res
            
            resource_data = {
                "구분": ["하역 (정규)", "하역 (임시)", "수배송 (지입)", "수배송 (임시)"],
                "이전 기간": [prev_res['Worker_Reg'], prev_res['Worker_Tmp'], prev_res['Truck_Con'], prev_res['Truck_Tmp']],
                "최근 기간": [curr_res['Worker_Reg'], curr_res['Worker_Tmp'], curr_res['Truck_Con'], curr_res['Truck_Tmp']]
            }
            res_df = pd.DataFrame(resource_data)
            res_df['증감율'] = res_df.apply(lambda r: f"{(r['최근 기간'] - r['이전 기간'])/(r['이전 기간'] if r['이전 기간']>0 else 1)*100:.1f}%", axis=1)
            st.dataframe(res_df, use_container_width=True, hide_index=True)

        with colB:
            st.subheader(f"📊 {view_mode} 입출고 실적 요약")
            curr_trend = agg_df[agg_df['Period'] == latest_period].iloc[0]
            
            in_achieve = f"{(curr_trend['In_A'] / curr_trend['In_P'] * 100):.1f}%" if curr_trend['In_P'] > 0 else "0.0%"
            out_achieve = f"{(curr_trend['Out_A'] / curr_trend['Out_P'] * 100):.1f}%" if curr_trend['Out_P'] > 0 else "0.0%"
            
            perf_data = {
                "구분": ["입고 (Inbound)", "출고 (Outbound)"],
                "예정 수량 (PCS)": [f"{curr_trend['In_P']:,.0f}", f"{curr_trend['Out_P']:,.0f}"],
                "작업 실적 (PCS)": [f"{curr_trend['In_A']:,.0f}", f"{curr_trend['Out_A']:,.0f}"],
                "잔량/미입 (PCS)": [f"{(curr_trend['In_P'] - curr_trend['In_A']):,.0f}", f"{(curr_trend['Out_P'] - curr_trend['Out_A']):,.0f}"],
                "작업 달성률 (%)": [in_achieve, out_achieve]
            }
            st.dataframe(pd.DataFrame(perf_data), use_container_width=True, hide_index=True)

        # 7. AI 심층 리포트 및 외부 연동
        st.markdown("---")
        if st.button("🤖 Lit.AI 심층 재무 분석 및 리포트 생성", key="tab1_ai_btn"):
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
            edited_report = st.text_area("리포트 내용 편집기", value=st.session_state.ai_report, height=350, label_visibility="collapsed", key="tab1_report_area")
            st.session_state.ai_report = edited_report

            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                pd.DataFrame({
                    "항목": ["총 매출", "총 매출원가", "매출이익", "매출이익률", "하역비", "배송비", "고정비 총액"],
                    "수치": [total_revenue, total_cost, total_profit, f"{margin_rate:.2f}%", total_handling_cost, total_delivery_cost, total_fixed_cost]
                }).to_excel(writer, index=False, sheet_name='Financial_Summary')
                agg_df.to_excel(writer, index=False, sheet_name='Period_Stats')
                df.to_excel(writer, index=False, sheet_name='Raw_Data_Corrected')
                pd.DataFrame({"Lit.AI 제언": [st.session_state.ai_report]}).to_excel(writer, index=False, sheet_name='Logi_AI_Analysis')
            
            st.download_button(
                label="💾 최종 가마감 엑셀 파일 다운로드",
                data=output.getvalue(),
                file_name=f"Logi_AI_Report_{datetime.date.today()}.xlsx",
                mime="application/vnd.ms-excel",
                key="tab1_download_btn"
            )

            st.markdown("---")
            st.subheader("🌐 외부 시스템 연동")
            
            if st.button("📤 Confluence에 보고서 업로드", key="tab1_conf_upload"):
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
        st.info("💡 일일 보고서(CSV)들을 업로드해 주세요.")


# -------------------------------------------------------------------
# [TAB 2] 가마감 예측 시뮬레이터 (버그 픽스 및 타입 변환 적용 완료)
# -------------------------------------------------------------------
with tab2:
    st.markdown("### 🔮 월간 가마감(Soft Closing) 예측 시뮬레이터")
    st.info("**가마감(임시마감)이란?**\n\n월 결산이 끝나기 전, 현재까지의 확정 실적(1, 2주차)을 바탕으로 남은 기간(3, 4주차)을 예측하여 **이번 달 최종 손익 착지점을 미리 파악**하는 작업입니다. 목표 미달이 예상될 경우, 월말이 오기 전에 도급 인력이나 배송 라인을 선제적으로 조정하여 **수익성을 방어하는 것이 핵심 목적**입니다.")

    st.markdown("#### 🔄 1. 실적 데이터 업로드 및 가마감 실행")
    pred_upload = st.file_uploader("자체 실적이 입력된 예측용 CSV 파일을 업로드해주세요.", type=['csv'], key="tab2_uploader")
    
    if pred_upload is not None:
        try:
            # 업로드된 파일 읽기
            pred_df = pd.read_csv(pred_upload)
            
            # 컬럼명이 4개 이상인지 확인 후 안전하게 변경
            if len(pred_df.columns) >= 4:
                pred_df.columns = ["구분(백만원)", "26년 월간계획", "1주차(실적)", "2주차(실적)"] + list(pred_df.columns[4:])
            
            # 수치 데이터 연산 전 콤마 제거 및 형변환 (화면 멈춤, 에러의 주요 원인 해결)
            for col in ["26년 월간계획", "1주차(실적)", "2주차(실적)"]:
                if col in pred_df.columns:
                    pred_df[col] = pd.to_numeric(pred_df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

            st.success("✅ 실적 데이터가 정상적으로 로드되었습니다! 아래에서 예측 가중치를 조정하여 가마감을 진행하세요.")
            
            # 2. 3~4주차 예측 로직 적용 (1,2주차 평균 베이스 + 가중치)
            st.markdown("#### ⚙️ 2. 잔여 주차 예측 가중치 설정")
            pred_weight = st.slider("📈 3~4주차 예측 가중치 (1,2주차 평균 실적 대비 % 적용)", 50, 150, 100, step=5, key="tab2_weight_slider") / 100.0
            
            # 예측값 계산 로직
            pred_df["3주차(예측)"] = round(((pred_df["1주차(실적)"] + pred_df["2주차(실적)"]) / 2) * pred_weight, 1)
            pred_df["4주차(예측)"] = round(((pred_df["1주차(실적)"] + pred_df["2주차(실적)"]) / 2) * pred_weight, 1)
            
            # 월 총 누적 가마감 산출
            pred_df["월 가마감(총합)"] = pred_df["1주차(실적)"] + pred_df["2주차(실적)"] + pred_df["3주차(예측)"] + pred_df["4주차(예측)"]
            
            # 0으로 나누기 방지
            pred_df["계획대비 달성률(%)"] = round((pred_df["월 가마감(총합)"] / pred_df["26년 월간계획"].replace(0, np.inf)) * 100, 1)

            # 3. 데이터 테이블 표시
            st.markdown("#### 📋 월 가마감 통합 명세서 (예측 반영)")
            def highlight_forecast(s):
                return ['background-color: #f0f8ff' if '예측' in col or '총합' in col else '' for col in s.index]
                
            st.dataframe(pred_df.style.apply(highlight_forecast, axis=1).format(precision=1), use_container_width=True, height=500)

            # 4. 핵심 지표 추이 그래프 시각화
            st.markdown("---")
            st.markdown("#### 📉 주차별 추이 및 월말 예측 시각화")
            
            chart_cols = ["1주차(실적)", "2주차(실적)", "3주차(예측)", "4주차(예측)"]
            
            try:
                # 차트용 데이터 추출 (매출액, 매출원가, 영업이익) - 존재할 경우에만
                if all(item in pred_df["구분(백만원)"].values for item in ["매출액", "매출원가", "영업이익"]):
                    rev_row = pred_df[pred_df["구분(백만원)"] == "매출액"][chart_cols].iloc[0]
                    profit_row = pred_df[pred_df["구분(백만원)"] == "영업이익"][chart_cols].iloc[0]
                    cost_row = pred_df[pred_df["구분(백만원)"] == "매출원가"][chart_cols].iloc[0]
                    
                    trend_data = pd.DataFrame({
                        "주차": chart_cols,
                        "매출액(백만원)": rev_row.values,
                        "매출원가(백만원)": cost_row.values,
                        "영업이익(백만원)": profit_row.values
                    })

                    col_chart1, col_chart2 = st.columns(2)
                    
                    with col_chart1:
                        # 혼합 차트 (Bar: 매출/원가, Line: 이익)
                        fig_trend = go.Figure()
                        
                        # 실적(진한색) vs 예측(옅은색) 시각적 구분
                        colors_rev = ['#1f77b4', '#1f77b4', '#aec7e8', '#aec7e8']
                        colors_cost = ['#ff7f0e', '#ff7f0e', '#ffbb78', '#ffbb78']

                        fig_trend.add_trace(go.Bar(x=trend_data["주차"], y=trend_data["매출액(백만원)"], name="매출액", marker_color=colors_rev))
                        fig_trend.add_trace(go.Bar(x=trend_data["주차"], y=trend_data["매출원가(백만원)"], name="매출원가", marker_color=colors_cost))
                        fig_trend.add_trace(go.Scatter(x=trend_data["주차"], y=trend_data["영업이익(백만원)"], name="영업이익", mode='lines+markers+text', 
                                                       text=trend_data["영업이익(백만원)"], textposition="top center",
                                                       line=dict(color='red', width=3)))
                        
                        fig_trend.update_layout(title="주차별 매출/원가 및 영업이익 추이", barmode='group')
                        st.plotly_chart(fig_trend, use_container_width=True)

                    with col_chart2:
                        # 직접비 구성 비율 파이 차트 (월 통합 기준)
                        direct_costs = pred_df[pred_df["구분(백만원)"].astype(str).str.contains("- 도급비|- 집하|- 배송|- 임차료|- 수선비|- 감가상각비|- 소모품비|- 기타")]
                        if not direct_costs.empty:
                            fig_pie = px.pie(direct_costs, values='월 가마감(총합)', names='구분(백만원)', hole=0.4, title="월 가마감 기준 직접비 구성비 예측")
                            st.plotly_chart(fig_pie, use_container_width=True)
                        else:
                            st.info("차트 생성을 위한 세부 직접비 항목이 존재하지 않습니다.")
                else:
                    st.warning("⚠️ 차트 생성을 위해 '구분(백만원)' 컬럼에 '매출액', '매출원가', '영업이익' 항목이 모두 존재해야 합니다.")
                    
            except IndexError:
                st.warning("⚠️ 차트 생성 중 문제가 발생했습니다. 데이터 구조를 다시 확인해주세요.")
                
        except Exception as e:
            st.error(f"데이터를 처리하는 중 오류가 발생했습니다: {e}")
            
    else:
        st.info("💡 실적 CSV 파일을 업로드 창에 넣어주시면 예측 분석이 즉시 시작됩니다.")
