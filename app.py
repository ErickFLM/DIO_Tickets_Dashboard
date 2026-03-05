import streamlit as st
import pandas as pd
import os
import time
import io
from datetime import datetime
import plotly.express as px
import pyrebase
from streamlit_gsheets import GSheetsConnection


# --- 1. CONFIGURAÇÃO DA PÁGINA (Deve ser o primeiro comando Streamlit) ---
st.set_page_config(
    page_title="Guardião DIO | Rastreabilidade & BI",
    page_icon="🛡️",
    layout="wide"
)

# --- 2. CONFIGURAÇÕES FIREBASE ---
# Substitua as strings abaixo pelas credenciais que você obteve no console do Firebase


firebase = pyrebase.initialize_app(firebase_config)
auth = firebase.auth()
conn = st.connection("gsheets", type=GSheetsConnection)




# --- 2. CAMADA DE DADOS ---
def inicializar_banco():
    colunas = [
        "ID", "Clínica", "Plano", "Plataforma", "Tipo", "Status", "Data_Abertura", 
        "D1_Feito", "D2_Feito", "D3_Feito", "Cobranças_Tech", "Notas", 
        "Data_Finalizacao", "Prioridade", "Motivo_Impedimento"
    ]
    
    try:
        url = st.secrets["connections"]["gsheets"]["url_tickets"]
        df = conn.read(spreadsheet=url, ttl=0)
        df['ID'] = df['ID'].astype(str).str.strip()
        df['Data_Abertura'] = pd.to_datetime(df['Data_Abertura'], dayfirst=True, errors='coerce')
        df['Data_Finalizacao'] = pd.to_datetime(df['Data_Finalizacao'], dayfirst=True, errors='coerce')
        
        for col in ["Notas", "Prioridade", "Data_Finalizacao", "Motivo_Impedimento", "Plataforma", "D2_Feito"]:
            if col not in df.columns: df[col] = ""
            
        df.fillna({
            'Notas': '', 'Prioridade': 'Normal', 'Cobranças_Tech': 0, 
            'Motivo_Impedimento': '', 'D1_Feito': 'Não', 'D2_Feito': 'Não', 'D3_Feito': 'Não',
            'Plataforma': 'DIO WEB'
            
        }, inplace=True)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar banco: {e}")
        return pd.DataFrame(columns=colunas)



def carregar_dados_churn():
    
    try:
        url = st.secrets["connections"]["gsheets"]["url_churn"]
        df = conn.read(spreadsheet=url, ttl="0")
        for col in ['Valor de ARR Perdido', 'Valor de MRR Perdido']:
            if col in df.columns and df[col].dtype == 'object':
                df[col] = df[col].str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).astype(float)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar base de churn: {e}")
        return pd.DataFrame()

def salvar_banco(df_entrada):
    # 1. Busca a URL da planilha nos segredos
    url = st.secrets["connections"]["gsheets"]["url_tickets"]
    
    df_save = df_entrada.copy()
    
    # 2. Formata as datas para texto (evita erro de serialização no Google)
    df_save['Data_Abertura'] = df_save['Data_Abertura'].dt.strftime('%d/%m/%Y %H:%M')
    df_save['Data_Finalizacao'] = pd.to_datetime(df_save['Data_Finalizacao']).dt.strftime('%d/%m/%Y %H:%M').fillna("")
    
    try:
        # 3. O PULO DO GATO: Envia o DataFrame inteiro para o Google Sheets
        # O parâmetro 'spreadsheet' recebe a URL, e 'data' recebe o seu DataFrame
        conn.update(spreadsheet=url, data=df_save)
        
        # 4. Limpa o cache para garantir que a próxima leitura pegue o dado novo
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")
        return False

# --- 3. INTELIGÊNCIA DE SLA (D1, D2, D3) ---
def engine_sla(row):
    if row['Status'] == "Finalizado": return "✅ Concluído"
    if pd.isnull(row['Data_Abertura']): return "⚪ Pendente"
    
    atraso = (datetime.now() - row['Data_Abertura']).total_seconds() / 86400
    
    if row['Prioridade'] == "Alta": return "🔥 PRIORIDADE ALTA"
    if atraso >= 3 and row['D3_Feito'] == "Não": return "🚨 CRÍTICO (D3 - 72h+)"
    if atraso >= 2 and row['D2_Feito'] == "Não": return "🟠 ALERTA 2 (D2 - 48h+)"
    if atraso >= 1 and row['D1_Feito'] == "Não": return "⚠️ ALERTA 1 (D1 - 24h+)"
    return "🟢 No Prazo"

# --- 4. EXPORTAÇÃO EXCEL ---
def preparar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Rastreabilidade_DIO')
        workbook  = writer.book
        worksheet = writer.sheets['Rastreabilidade_DIO']
        header_fmt = workbook.add_format({'bold': True, 'fg_color': '#1F4E78', 'font_color': 'white', 'border': 1})
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
        for i, col in enumerate(df.columns):
            worksheet.set_column(i, i, 20)
    return output.getvalue()


    # --- 5. LÓGICA DE AUTENTICAÇÃO ---
def tela_login():
    st.markdown("<br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])

    with c2:
        st.title("🛡️ Guardião DIO")
        st.subheader("Login de Acesso")

        with st.form("login_form"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            btn = st.form_submit_button("Entrar", use_container_width=True)

            if btn:

                if not email or not password:
                    st.warning("Preencha e-mail e senha.")
                    return

                try:
                    user = auth.sign_in_with_email_and_password(email, password)

                    # 🔥 atualiza sessão antes de rerun
                    st.session_state.authenticated = True
                    st.session_state.user = user
                    st.success("Login realizado com sucesso!")

                    time.sleep(0.5)
                    st.rerun()

                except Exception as e:
                    st.error("E-mail ou senha incorretos.")
# ---------------- CONTROLE DE SESSÃO ---------------- #

if 'authenticated' not in st.session_state:
    tela_login()
    st.stop()

# ---------------- APP PRINCIPAL ---------------- #

df_raw = inicializar_banco()

if not df_raw.empty:
    df_raw['SLA_Status'] = df_raw.apply(engine_sla, axis=1)
else:
    df_raw['SLA_Status'] = ""

urgentes_count = len(df_raw[df_raw['SLA_Status'].str.contains("🚨|🔥|🟠")])

# --- 6. INTERFACE STREAMLIT ---
st.title("🛡️ Guardião DIO - Gestão de Erros & Rastreabilidade")

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2092/2092663.png", width=80)
    st.header("Painel Administrativo")
    
    with st.expander("🆕 Novo Registro Retroativo"):
        with st.form("form_novo", clear_on_submit=True):
            f_clinica = st.text_input("Nome da Clínica")
            f_plat = st.selectbox("Plataforma", ["DIO WEB", "Integra-AI", "Outros"])
            f_plano = st.selectbox("Plano", [10, 25, 50, 100, 200, 999])
            f_tipo = st.selectbox("Tipo de Erro", ["Instalação", "Bug", "Configuração", "Treinamento", "Integração"])
            
            st.write("**Data de Abertura:**") 
            col_d1, col_d2 = st.columns(2)
            sel_data = col_d1.date_input("Dia", datetime.now())
            sel_hora = col_d2.time_input("Hora", datetime.now().time())
            f_abertura = datetime.combine(sel_data, sel_hora)
            
            f_prio = st.select_slider("Prioridade", options=["Normal", "Alta"])

            if st.form_submit_button("Lançar no Histórico"): 
                if f_clinica:
                    novo_id = str(int(time.time() * 1000))
                    nova = {
                        "ID": novo_id,
                        "Clínica": f_clinica,
                        "Plataforma": f_plat,
                        "Plano": f_plano,
                        "Tipo": f_tipo,
                        "Status": "Novo",
                        "Data_Abertura": f_abertura,
                        "D1_Feito": "Não",
                        "D2_Feito": "Não",
                        "D3_Feito": "Não",
                        "Cobranças_Tech": 0,
                        "Notas": "",
                        "Data_Finalizacao": "",
                        "Prioridade": f_prio,
                        "Motivo_Impedimento": ""
                    }
                    df_raw = pd.concat([df_raw, pd.DataFrame([nova])], ignore_index=True)
                    salvar_banco(df_raw)
                    st.rerun()

    st.markdown("---")

    status_opcoes = [
        "Novo",
        "Aguardando Tech",
        "Ação Suporte",
        "Aguardando Cliente",
        "Finalizado",
        "Aguardando Equipe Academica"
    ]

    f_status = st.multiselect(
        "Filtrar Visão:",
        status_opcoes,
        default=[
            "Novo",
            "Aguardando Tech",
            "Ação Suporte",
            "Aguardando Cliente",
            "Aguardando Equipe Academica"
        ]
    )

    busca = st.text_input("🔍 Buscar Clínica...")

    df_view = df_raw[df_raw['Status'].isin(f_status)].copy() if not df_raw.empty else df_raw.copy()

    if busca:
        df_view = df_view[df_view['Clínica'].str.contains(busca, case=False)]

    st.markdown("---")

    # 🔒 BOTÃO DE LOGOUT (AGORA DENTRO DA SIDEBAR)
    if st.button("🚪 Sair do Sistema", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# ABAS
tab_ops, tab_bi, tab_hist, tab_churn  = st.tabs(["🚀 Operação Suporte", "📊 BI & Causa Raiz", "📁 Exportação Excel", "📉 Gestão de Churn"])

with tab_ops:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fila Ativa", len(df_view))
    tech_gargalo = len(df_view[df_view['Status'] == "Aguardando Tech"])
    c2.metric("Gargalo Tech", tech_gargalo, delta="Ação Necessária", delta_color="inverse")
    c3.metric("Urgência SLA", urgentes_count, delta="Crítico", delta_color="inverse")
    c4.metric("Contas VIP", len(df_view[df_view['Plano'] >= 100]))

    st.markdown("---")

    if not df_view.empty:
        with st.container(border=True):
            opcoes_lista = df_view.apply(lambda r: f"{r['ID']} | {r['Clínica']}", axis=1).tolist()
            selecao = st.selectbox("Selecione o Ticket:", opcoes_lista)
            id_atual = selecao.split(" | ")[0]
            ticket = df_raw[df_raw['ID'] == id_atual].iloc[0]

            with st.form(key=f"edicao_{id_atual}"):
                col_e1, col_e2 = st.columns([1, 2])
                with col_e1:
                    novo_st = st.selectbox("Status", status_opcoes, index=status_opcoes.index(ticket['Status']))
                    
                    st.write("**Data de Conclusão:**")
                    d_base = ticket['Data_Finalizacao'] if pd.notnull(ticket['Data_Finalizacao']) else datetime.now()
                    col_f1, col_f2 = st.columns(2)
                    data_f = col_f1.date_input("Dia", d_base)
                    hora_f = col_f2.time_input("Hora", d_base.time() if hasattr(d_base, 'time') else datetime.now().time())
                    
                    lista_motivos = ["", "Falta de Acesso Remoto", "Bug de Software", "Aguardando Cliente", "Infraestrutura", "Erro de Terceiros", "Treinamento"]
                    motivo_idx = lista_motivos.index(ticket['Motivo_Impedimento']) if ticket['Motivo_Impedimento'] in lista_motivos else 0
                    novo_motivo = st.selectbox("Causa Raiz", lista_motivos, index=motivo_idx)
                    
                    st.write("**Régua SLA:**")
                    c_d1 = st.checkbox("D1 Ok", value=(ticket['D1_Feito'] == "Sim"))
                    c_d2 = st.checkbox("D2 Ok", value=(ticket['D2_Feito'] == "Sim"))
                    c_d3 = st.checkbox("D3 Ok", value=(ticket['D3_Feito'] == "Sim"))
                    
                    # --- AQUI ESTÁ O CHECKBOX QUE FALTAVA A LÓGICA ---
                    add_cob = st.checkbox("Somar Cobrança Tech (+1)")

                with col_e2:
                    st.write("**Histórico Log:**")
                    st.text_area("Notas:", value=ticket['Notas'], height=150, disabled=True)
                    f_nova_nota = st.text_input("Adicionar Nota:")

                if st.form_submit_button("💾 Salvar Alterações", type="primary"):
                    idx = df_raw[df_raw['ID'] == id_atual].index[0]
                    df_raw.at[idx, 'Status'] = novo_st
                    df_raw.at[idx, 'Motivo_Impedimento'] = novo_motivo
                    df_raw.at[idx, 'D1_Feito'] = "Sim" if c_d1 else "Não"
                    df_raw.at[idx, 'D2_Feito'] = "Sim" if c_d2 else "Não"
                    df_raw.at[idx, 'D3_Feito'] = "Sim" if c_d3 else "Não"
                    
                    # --- LÓGICA DE INCREMENTO DAS COBRANÇAS TECH ---
                    if add_cob:
                        df_raw.at[idx, 'Cobranças_Tech'] += 1
                    
                    if f_nova_nota:
                        df_raw.at[idx, 'Notas'] = f"[{datetime.now().strftime('%d/%m %H:%M')}] {f_nova_nota}\n{ticket['Notas']}".strip()
                    if novo_st == "Finalizado":
                        df_raw.at[idx, 'Data_Finalizacao'] = datetime.combine(data_f, hora_f)
                    
                    salvar_banco(df_raw); st.rerun()

    st.dataframe(df_view[['SLA_Status', 'Plataforma', 'Clínica', 'Status', 'Cobranças_Tech', 'Motivo_Impedimento']], use_container_width=True, hide_index=True)

with tab_bi:
    st.header("📊 Inteligência de Suporte DIO WEB")
    if not df_raw.empty:
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.pie(df_raw, names='Plataforma', title="Volume por Sistema", hole=0.4), use_container_width=True)
        with g2:
            df_motivos = df_raw[df_raw['Motivo_Impedimento'].str.strip() != ""].copy()
            if not df_motivos.empty:
                st.plotly_chart(px.pie(df_motivos, names='Motivo_Impedimento', title="Análise de Causa Raiz", hole=0.4), use_container_width=True)
            else:
                st.info("Lance as 'Causas Raiz' nos tickets para gerar este gráfico.")
        
        st.plotly_chart(px.bar(df_raw, x='Tipo', color='Plataforma', title="Categorias de Erro"), use_container_width=True)

with tab_hist:
    st.header("📁 Rastreabilidade Completa (desde Nov/23)")
    excel_data = preparar_excel(df_raw)
    st.download_button("📥 Exportar Planilha DIO WEB (Excel)", excel_data, f"Rastreabilidade_DIO_{datetime.now().strftime('%d_%m')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.dataframe(df_raw, use_container_width=True, hide_index=True)

with tab_churn:
    st.header("📉 Análise Estratégica de Churn (Retenção)")
    df_churn = carregar_dados_churn()
    
    # --- 1. LIMPEZA E PADRONIZAÇÃO (EXATAMENTE COMO O SEU ORIGINAL) ---
    df_churn = df_churn.fillna("Não informado")
    df_churn['Submotivo'] = df_churn['Submotivo'].replace("Nan", "Outros")
    df_churn['Motivo de Churn'] = df_churn['Motivo de Churn'].replace("Nan", "Não categorizado")
    
    if df_churn.empty:
        st.warning("⚠️ Base de Churn não encontrada.")
    else:
        # Garantindo que 'Análises' seja texto para o filtro não quebrar
        df_churn['Análises'] = df_churn['Análises'].astype(str).str.strip()
        
        df_churn['Motivo de Churn'] = df_churn['Motivo de Churn'].astype(str).str.strip().str.capitalize()
        df_churn['Submotivo'] = df_churn['Submotivo'].astype(str).str.strip().str.capitalize()
        df_churn['Mês'] = df_churn['Mês'].astype(str).str.strip().str.capitalize()

        # --- 2. FILTROS (MANTENDO OS SEUS + ADICIONANDO ANÁLISES) ---
        with st.container(border=True):
            f1, f2, f3, f4 = st.columns([1, 1, 1, 1])
            anos = sorted(df_churn['Ano'].unique())
            sel_ano = f1.multiselect("Ano:", anos, default=anos)
            
            css = sorted(df_churn['CS'].unique())
            sel_cs = f2.multiselect("Responsável (CS):", css, default=css)

            # ADICIONADO: Filtro de Análises
            analises_list = sorted(df_churn['Análises'].unique())
            sel_analises = f3.multiselect("Nº Análises (Plano):", analises_list, default=analises_list)
            
            busca_cliente = f4.text_input("🔍 Localizar Clínica:")
            
            # Filtro mestre respeitando todos os campos
            df_c_filtered = df_churn[
                (df_churn['Ano'].isin(sel_ano)) & 
                (df_churn['CS'].isin(sel_cs)) &
                (df_churn['Análises'].isin(sel_analises))
            ]
            if busca_cliente:
                df_c_filtered = df_c_filtered[df_c_filtered['Cliente'].str.contains(busca_cliente, case=False)]

        st.write("") 

        # --- 3. KPIs (ORIGINAIS) ---
        mrr_total = df_c_filtered['Valor de MRR Perdido'].sum()
        arr_total = df_c_filtered['Valor de ARR Perdido'].sum()
        qtd_churn = len(df_c_filtered)
        
        c1, c2, c3 = st.columns(3)
        with c1:
            with st.container(border=True):
                st.metric("🏥 Clínicas Perdidas", f"{qtd_churn} un")
        with c2:
            with st.container(border=True):
                st.metric("💸 Perda MRR", f"R$ {mrr_total:,.2f}")
        with c3:
            with st.container(border=True):
                st.metric("💰 Perda ARR", f"R$ {arr_total:,.2f}")

        st.write("") 

        # --- 4. SEÇÃO: MOTIVOS (INTERATIVO - ORIGINAL) ---
        with st.container(border=True):
            col_t1, col_t2 = st.columns([2, 1])
            col_t1.subheader("🚩 1. Principais Motivos de Saída")
            metrica_motivo = col_t2.radio("Visualizar por:", ["Valor (R$)", "Quantidade (Nº)"], key="met_mot", horizontal=True)

            df_motivo = df_c_filtered.groupby('Motivo de Churn').agg(
                Valor=('Valor de MRR Perdido', 'sum'),
                Quantidade=('Motivo de Churn', 'count')
            ).reset_index()

            eixo_x = 'Valor' if metrica_motivo == "Valor (R$)" else 'Quantidade'
            label_x = "Prejuízo MRR (R$)" if eixo_x == 'Valor' else "Qtd. de Clínicas"
            cor_escala = 'Reds' if eixo_x == 'Valor' else 'Blues'

            fig_motivo = px.bar(
                df_motivo.sort_values(eixo_x), x=eixo_x, y='Motivo de Churn',
                orientation='h', color=eixo_x, color_continuous_scale=cor_escala,
                text_auto='.2s'
            )
            fig_motivo.update_layout(height=450, showlegend=False, yaxis_title=None, xaxis_title=label_x)
            st.plotly_chart(fig_motivo, use_container_width=True)

        st.write("") 

        # --- 5. SEÇÃO: SUBMOTIVOS (INTERATIVO - ORIGINAL) ---
        with st.container(border=True):
            col_st1, col_st2 = st.columns([2, 1])
            col_st1.subheader("🔍 2. Detalhes Específicos (Submotivos)")
            metrica_sub = col_st2.radio("Visualizar por:", ["Valor (R$)", "Quantidade (Nº)"], key="met_sub", horizontal=True)

            df_sub = df_c_filtered.groupby('Submotivo').agg(
                Valor=('Valor de MRR Perdido', 'sum'),
                Quantidade=('Submotivo', 'count')
            ).reset_index()

            eixo_x_sub = 'Valor' if metrica_sub == "Valor (R$)" else 'Quantidade'
            label_x_sub = "Prejuízo MRR (R$)" if eixo_x_sub == 'Valor' else "Qtd. de Clínicas"
            cor_escala_sub = 'Purples' if eixo_x_sub == 'Valor' else 'GnBu'

            fig_sub = px.bar(
                df_sub.sort_values(eixo_x_sub), x=eixo_x_sub, y='Submotivo',
                orientation='h', color=eixo_x_sub, color_continuous_scale=cor_escala_sub,
                text_auto='.2s'
            )
            fig_sub.update_layout(height=600, showlegend=False, yaxis_title=None, xaxis_title=label_x_sub)
            st.plotly_chart(fig_sub, use_container_width=True)

        st.write("")

     # --- 6. NOVA SEÇÃO: INVESTIGAÇÃO POR CS (ORGANIZADA POR QUANTIDADE) ---
        with st.container(border=True):
            st.subheader("🕵️ 3. Investigação por Analista CS")
            st.write("Análise de volume de saídas por plano e impacto financeiro.")
            
            # Lista com opção global
            lista_cs_detalhe = ["Todas as CSs"] + sorted(df_c_filtered['CS'].unique().tolist())
            sel_cs_drill = st.selectbox("Selecione o CS para abrir a carteira:", lista_cs_detalhe)
            
            # Lógica de filtro
            if sel_cs_drill == "Todas as CSs":
                df_drill = df_c_filtered
                titulo_visao = "Carteira Global (Todas as CSs)"
            else:
                df_drill = df_c_filtered[df_c_filtered['CS'] == sel_cs_drill]
                titulo_visao = f"Analista: {sel_cs_drill}"
            
            # --- O PULO DO GATO: Agrupar para a Pizza ---
            # Agrupamos por plano para ter a contagem (fatias) e a soma (hover)
            df_drill_pie = df_drill.groupby('Análises').agg(
                Qtd=('Análises', 'count'),
                MRR_Total=('Valor de MRR Perdido', 'sum')
            ).reset_index()

            d1, d2 = st.columns([1, 1.5])
            with d1:
                st.markdown(f"#### 📊 {titulo_visao}")
                st.write(f"**Total de Clínicas Perdidas:** {len(df_drill)}")
                
                # Tabela de apoio (Quantidade)
                df_count_drill = df_drill_pie[['Análises', 'Qtd']].sort_values('Qtd', ascending=False)
                df_count_drill.columns = ['Plano (Análises)', 'Qtd Clínicas']
                st.table(df_count_drill)
            
            with d2:
                # Gráfico de Pizza organizado por QUANTIDADE
                fig_pie_drill = px.pie(
                    df_drill_pie, 
                    names='Análises', 
                    values='Qtd',  # Agora a fatia é definida pelo número de clínicas
                    title=f"Volume de Saídas por Plano - {titulo_visao}",
                    hole=0.4, 
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    # Adicionamos o MRR no hover para aparecer ao passar o mouse
                    hover_data={'MRR_Total': ':,.2f', 'Qtd': True}
                )
                
                # Customização do texto que aparece no hover
                fig_pie_drill.update_traces(
                    hovertemplate="<b>Plano: %{label}</b><br>Qtd: %{value}<br>Perda Financeira: R$ %{customdata[0]:,.2f}"
                )
                
                st.plotly_chart(fig_pie_drill, use_container_width=True)

        # --- 7. LINHA DO TEMPO (ORIGINAL) ---
        with st.container(border=True):
            st.subheader("📅 4. Evolução do Churn no Tempo")
            meses_ordem = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
                           "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            
            df_evol = df_c_filtered.groupby(['Ano', 'Mês']).agg(Valor=('Valor de MRR Perdido', 'sum')).reset_index()
            df_evol['Mês'] = pd.Categorical(df_evol['Mês'], categories=meses_ordem, ordered=True)
            df_evol = df_evol.sort_values(['Ano', 'Mês'])
            
            fig_evol = px.line(
                df_evol, x='Mês', y='Valor', color='Ano',
                markers=True, text='Valor', category_orders={"Mês": meses_ordem}
            )
            fig_evol.update_traces(texttemplate='%{text:.2s}', textposition='top center')
            fig_evol.update_layout(height=500, xaxis_title=None, yaxis_title="R$ Perdido (MRR)")
            st.plotly_chart(fig_evol, use_container_width=True)

        with st.expander("📄 Ver Detalhes dos Clientes"):
            st.dataframe(df_c_filtered[['Cliente', 'CS', 'Análises', 'Motivo de Churn', 'Valor de MRR Perdido', 'Mês']], use_container_width=True, hide_index=True)