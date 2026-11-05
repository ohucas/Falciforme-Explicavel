from pathlib import Path
import streamlit as st
from src.pesquisa.ui import painel_treinamento

st.set_page_config(page_title="Falciforme Explicável - Pesquisa", layout="wide")
st.title("Experimentos e treinamento")
st.caption("Ferramenta do pesquisador, separada da interface de atendimento.")
st.warning(
    "Treinar um modelo não o valida para uso clínico nem o disponibiliza automaticamente no aplicativo médico."
)
if st.button("Encerrar experimento e limpar sessão"):
    st.session_state.clear()
    st.rerun()
painel_treinamento("pesquisador")
st.info(
    "Os modelos treinados permanecem somente nesta sessão. A integração de um modelo revisado ao atendimento será uma etapa posterior; nenhum modelo é transferido silenciosamente entre aplicações."
)
