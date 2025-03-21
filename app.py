import streamlit as st
import os
import tempfile
import re
import zipfile
from PyPDF2 import PdfReader, PdfMerger

def extrair_texto_pdf(arquivo):
    """Extrai texto do PDF."""
    try:
        reader = PdfReader(arquivo)
        texto = ""
        for page in reader.pages:
            texto += page.extract_text()
        return texto
    except Exception as e:
        st.error(f"Erro na extração do texto do arquivo {arquivo.name}: {str(e)}")
        return ""

def encontrar_cnpj(texto):
    """Busca CNPJs no conteúdo do PDF e padroniza a formatação."""
    padrao_cnpj = re.findall(r"\b\d{2}[.\/]?\d{3}[.\/]?\d{3}[\/\-]?\d{4}[\/\-]?\d{2}\b", texto)
    cnpjs = {re.sub(r'[^\d]', '', cnpj) for cnpj in padrao_cnpj} if padrao_cnpj else set()
    return cnpjs

def encontrar_valor_darf(texto):
    """Busca valores monetários no DARF (após 'Vl.Recolhe')."""
    padrao_valor = re.findall(r"Vl\.Recolhe\s*([\d.,]+)", texto)
    valores = {float(valor.replace('.', '').replace(',', '.')) for valor in padrao_valor} if padrao_valor else set()
    return valores

def encontrar_valor_comprovante(texto):
    """Busca valores monetários no comprovante (após 'VALOR DO PRINCIPAL')."""
    padrao_valor = re.findall(r"VALOR DO PRINCIPAL\s*R\$\s*([\d.,]+)", texto)
    valores = {float(valor.replace('.', '').replace(',', '.')) for valor in padrao_valor} if padrao_valor else set()
    return valores

def organizar_por_cnpj_e_valor(arquivos):
    st.write("### Processando arquivos...")
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "darfs_agrupados.zip")
    pdf_resultados = {}
    agrupados = {}
    info_arquivos = []
    
    # Extrai informações dos arquivos
    for arquivo in arquivos:
        nome = arquivo.name
        texto_pdf = extrair_texto_pdf(arquivo)
        cnpjs = encontrar_cnpj(texto_pdf)
        
        if "DARF" in nome:
            valores = encontrar_valor_darf(texto_pdf)
            info_arquivos.append((arquivo, nome, valores, cnpjs, "DARF"))
        elif "Comprovante" in nome:
            valores = encontrar_valor_comprovante(texto_pdf)
            info_arquivos.append((arquivo, nome, valores, cnpjs, "Comprovante"))
    
    # Associa DARFs e comprovantes
    for darf, nome_darf, valores_darf, cnpjs_darf, tipo_darf in info_arquivos:
        if tipo_darf != "DARF":
            continue  # Ignora arquivos que não são DARFs
        
        for comprovante, nome_comp, valores_comp, cnpjs_comp, tipo_comp in info_arquivos:
            if tipo_comp == "Comprovante":
                # Verifica correspondência de CNPJ e valor
                if cnpjs_darf & cnpjs_comp and valores_darf & valores_comp:
                    agrupados[nome_darf] = [darf, comprovante]
                    break
    
    # Gera PDFs agrupados e arquivo ZIP
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for nome_final, arquivos in agrupados.items():
            merger = PdfMerger()
            for doc in arquivos:
                merger.append(doc)
            output_filename = f"Agrupado_{nome_final}"
            output_path = os.path.join(temp_dir, output_filename)
            merger.write(output_path)
            merger.close()
            pdf_resultados[output_filename] = output_path
            zipf.write(output_path, arcname=output_filename)
            st.write(f"📂 Arquivo gerado: {output_filename}")
    
    return pdf_resultados, zip_path

def main():
    st.title("Agrupador de DARFs e Comprovantes")
    
    # Adicionando um key único ao file_uploader
    arquivos = st.file_uploader("Envie seus arquivos", accept_multiple_files=True, key="file_uploader")
    
    if arquivos and len(arquivos) > 0:
        if st.button("🔗 Juntar e Processar PDFs", key="process_button"):
            pdf_resultados, zip_path = organizar_por_cnpj_e_valor(arquivos)
            
            for nome, caminho in pdf_resultados.items():
                with open(caminho, "rb") as f:
                    st.download_button(
                        label=f"📄 Baixar {nome}",
                        data=f,
                        file_name=nome,
                        mime="application/pdf",
                        key=f"download_{nome}"  # Adicionando um key único para cada botão de download
                    )
            
            with open(zip_path, "rb") as f:
                st.download_button(
                    label="📥 Baixar todos como ZIP",
                    data=f,
                    file_name="darfs_agrupados.zip",
                    mime="application/zip",
                    key="download_zip"  # Adicionando um key único para o botão de download do ZIP
                )

if __name__ == "__main__":
    main()
