import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime
import plotly.express as px

# --- 1. CONFIGURAÇÕES TÉCNICAS E DESIGN ---
st.set_page_config(
    page_title="Guardião Integra-AI | Sistema de Elite",
    page_icon="🛡️",
    layout="wide"
)

DB_FILE = "base_suporte.csv"

# --- 2. CAMADA DE ACESSO A DADOS (DATA ACCESS LAYER) ---
def inicializar_banco():
    colunas = [
        "ID", "Clínica", "Plano", "Tipo", "Status", "Data_Abertura", 
        "D1_Feito", "D3_Feito", "Cobranças_Tech", "Notas", "Data_Finalizacao", 
        "Prioridade", "Motivo_Impedimento"
    ]
    if not os.path.exists(DB_FILE):
        df = pd.DataFrame(columns=colunas)
        df.to_csv(DB_FILE, index=False)
        return df
    try:
        df = pd.read_csv(DB_FILE)
        df['ID'] = df['ID'].astype(str).str.strip()
        df['Data_Abertura'] = pd.to_datetime(df['Data_Abertura'], dayfirst=True, errors='coerce')
        
        # Injeção de colunas novas para retrocompatibilidade
        for col in ["Notas", "Prioridade", "Data_Finalizacao", "Motivo_Impedimento"]:
            if col not in df.columns: df[col] = ""
            
        df.fillna({'Notas': '', 'Prioridade': 'Normal', 'Cobranças_Tech': 0, 'Motivo_Impedimento': ''}, inplace=True)
        return df
    except Exception as e:
        st.error(f"Erro ao acessar banco de dados: {e}")
        return pd.DataFrame(columns=colunas)

def salvar_banco(df_entrada):
    df_save = df_entrada.copy()
    df_save['Data_Abertura'] = df_save['Data_Abertura'].dt.strftime('%d/%m/%Y %H:%M')
    if 'Data_Finalizacao' in df_save.columns:
        df_save['Data_Finalizacao'] = pd.to_datetime(df_save['Data_Finalizacao'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M').fillna("")
    
    for _ in range(10):
        try:
            df_save.to_csv(DB_FILE, index=False)
            return True
        except: time.sleep(0.1)
    return False

# --- 3. REGRAS DE INTELIGÊNCIA ---
def engine_sla(row):
    if row['Status'] == "Finalizado": return "✅ Concluído"
    if pd.isnull(row['Data_Abertura']): return "⚪ Aguardando"
    
    dias_atraso = (datetime.now() - row['Data_Abertura']).total_seconds() / 86400
    
    if row['Prioridade'] == "Alta": return "🔥 PRIORIDADE ALTA"
    if dias_atraso >= 3 and row['D3_Feito'] == "Não": return "🚨 CRÍTICO (72h+)"
    if dias_atraso >= 1 and row['D1_Feito'] == "Não": return "⚠️ ALERTA (24h+)"
    return "🟢 No Prazo"

# --- 4. PIPELINE DE CARREGAMENTO ---
df_raw = inicializar_banco()
if not df_raw.empty:
    df_raw['SLA_Status'] = df_raw.apply(engine_sla, axis=1)
else:
    df_raw['SLA_Status'] = ""

# --- 5. INTERFACE DO USUÁRIO ---
st.title("🛡️ Sistema Guardião - Suporte Integra-AI")

# ALERTA AUTOMÁTICO (TOAST) AO CARREGAR
# Ele avisa se houver algo crítico logo que você abre o app
urgentes = len(df_raw[df_raw['SLA_Status'].str.contains("🚨|🔥")])
if urgentes > 0:
    st.toast(f"Atenção: Você tem {urgentes} tickets em estado CRÍTICO!", icon="🚨")

# SIDEBAR: CADASTRO E FILTROS
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2092/2092663.png", width=80)
    st.header("Menu de Controle")
    
    with st.expander("🆕 Abrir Novo Chamado"):
        with st.form("form_cadastro", clear_on_submit=True):
            f_clinica = st.text_input("Nome da Clínica")
            f_plano = st.selectbox("Plano", [10, 25, 50, 100, 200])
            f_tipo = st.selectbox("Tipo", ["Instalação", "Bug", "Configuração", "Integração"])
            f_prio = st.select_slider("Prioridade", options=["Normal", "Alta"])
            
            if st.form_submit_button("Cadastrar"):
                if f_clinica:
                    novo_id = str(int(time.time() * 1000))
                    nova_linha = {
                        "ID": novo_id, "Clínica": f_clinica, "Plano": f_plano, "Tipo": f_tipo,
                        "Status": "Novo", "Data_Abertura": datetime.now(), "D1_Feito": "Não",
                        "D3_Feito": "Não", "Cobranças_Tech": 0, "Notas": "", 
                        "Data_Finalizacao": "", "Prioridade": f_prio, "Motivo_Impedimento": ""
                    }
                    df_raw = pd.concat([df_raw, pd.DataFrame([nova_linha])], ignore_index=True)
                    salvar_banco(df_raw); st.rerun()

    st.markdown("---")
    # Busca Global (Sugestão Extra)
    busca = st.text_input("🔍 Buscar Clínica...")
    
    status_list = df_raw['Status'].unique().tolist() if not df_raw.empty else ["Novo"]
    f_status = st.multiselect("Status", status_list, default=[s for s in status_list if s != "Finalizado"])
    
    df_view = df_raw[df_raw['Status'].isin(f_status)].copy()
    if busca:
        df_view = df_view[df_view['Clínica'].str.contains(busca, case=False)]

# ABAS
tab_ops, tab_bi, tab_hist = st.tabs(["🚀 Operação Suporte", "📊 BI & Relatórios", "📁 Arquivo Geral"])

with tab_ops:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fila Atual", len(df_view))
    c2.metric("Urgentes", urgentes, delta="Atenção", delta_color="inverse")
    c3.metric("Gargalo Tech", len(df_view[df_view['Status'] == "Aguardando Tech"]))
    c4.metric("Contas VIP", len(df_view[df_view['Plano'] >= 100]))

    st.markdown("---")

    if not df_view.empty:
        with st.container(border=True):
            opcoes_select = df_view.apply(lambda r: f"{r['ID']} | {r['Clínica']}", axis=1).tolist()
            selecao_id = st.selectbox("Selecione o Ticket:", opcoes_select)
            id_atual = selecao_id.split(" | ")[0]
            ticket_row = df_raw[df_raw['ID'] == id_atual].iloc[0]

            with st.form(key=f"editor_{id_atual}"):
                col_e1, col_e2 = st.columns([1, 2])
                with col_e1:
                    st.write(f"**Gestão:** {ticket_row['Clínica']}")
                    novo_st = st.selectbox("Status", ["Novo", "Aguardando Tech", "Ação Suporte", "Aguardando Cliente", "Finalizado"], 
                                           index=["Novo", "Aguardando Tech", "Ação Suporte", "Aguardando Cliente", "Finalizado"].index(ticket_row['Status']))
                    
                    # --- IMPLEMENTAÇÃO CAUSA RAIZ ---
                    motivos = ["", "Falta de Acesso Remoto", "Bug de Software", "Aguardando Cliente", "Infraestrutura", "Erro de Terceiros"]
                    motivo_idx = motivos.index(ticket_row['Motivo_Impedimento']) if ticket_row['Motivo_Impedimento'] in motivos else 0
                    novo_motivo = st.selectbox("Motivo do Impedimento", motivos, index=motivo_idx)
                    
                    nova_prio = st.selectbox("Prioridade", ["Normal", "Alta"], index=["Normal", "Alta"].index(ticket_row['Prioridade']))
                    c_d1 = st.checkbox("D1 Ok", value=(ticket_row['D1_Feito'] == "Sim"))
                    c_d3 = st.checkbox("D3 Ok", value=(ticket_row['D3_Feito'] == "Sim"))
                    add_cob = st.checkbox("Somar Cobrança Tech")

                with col_e2:
                    st.write("**Histórico:**")
                    st.text_area("Notas:", value=ticket_row['Notas'], height=120, disabled=True)
                    f_nova_nota = st.text_input("Nova nota:")

                if st.form_submit_button("💾 Salvar Alterações", type="primary"):
                    idx = df_raw[df_raw['ID'] == id_atual].index[0]
                    df_raw.at[idx, 'Status'] = novo_st
                    df_raw.at[idx, 'Motivo_Impedimento'] = novo_motivo
                    df_raw.at[idx, 'Prioridade'] = nova_prio
                    df_raw.at[idx, 'D1_Feito'] = "Sim" if c_d1 else "Não"
                    df_raw.at[idx, 'D3_Feito'] = "Sim" if c_d3 else "Não"
                    if add_cob: df_raw.at[idx, 'Cobranças_Tech'] += 1
                    if f_nova_nota:
                        df_raw.at[idx, 'Notas'] = f"[{datetime.now().strftime('%d/%m %H:%M')}] {f_nova_nota}\n{ticket_row['Notas']}".strip()
                    if novo_st == "Finalizado": df_raw.at[idx, 'Data_Finalizacao'] = datetime.now()
                    
                    salvar_banco(df_raw); st.rerun()

    st.dataframe(df_view[['SLA_Status', 'Status', 'Clínica', 'Tipo', 'Motivo_Impedimento', 'Cobranças_Tech']], use_container_width=True, hide_index=True)

with tab_bi:
    st.header("📊 BI & Relatórios")
    if not df_raw.empty:
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.pie(df_raw, names='Status', title="Status Geral", hole=0.4), use_container_width=True)
        with g2:
            # --- GRÁFICO DE CAUSA RAIZ ---
            df_motivos = df_raw[df_raw['Motivo_Impedimento'] != ""].copy()
            if not df_motivos.empty:
                st.plotly_chart(px.pie(df_motivos, names='Motivo_Impedimento', title="Análise de Causa Raiz", hole=0.4), use_container_width=True)
            else: st.info("Sem dados de Causa Raiz.")
        
        st.plotly_chart(px.bar(df_raw, x='Tipo', color='Status', title="Volume por Categoria"), use_container_width=True)

with tab_hist:
    st.header("📁 Histórico Completo")
    st.download_button("📥 Exportar CSV", df_raw.to_csv(index=False).encode('utf-8'), "relatorio_cs.csv", "text/csv")
    st.dataframe(df_raw, use_container_width=True, hide_index=True)