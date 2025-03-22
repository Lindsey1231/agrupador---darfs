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

def encontrar_nome_fornecedor(texto, tipo_arquivo):
    """Busca o nome do fornecedor no conteúdo do PDF."""
    if tipo_arquivo == "DARF":
        # Extrai o nome do fornecedor após "Parceiro :"
        padrao_nome = re.findall(r"Parceiro\s*:\s*([\w\s]+?)\s*\d", texto)
    elif tipo_arquivo == "Comprovante":
        # Extrai o nome do fornecedor após "Nome:"
        padrao_nome = re.findall(r"Nome\s*:\s*([\w\s]+?)\n", texto)
    else:
        return set()
    
    return set(padrao_nome)  # Usamos um set para facilitar a comparação

def encontrar_valor_darf(texto):
    """Busca valores monetários no DARF (após 'Vl.Recolhe :')."""
    padrao_valor = re.findall(r"Vl\.Recolhe\s*:\s*([\d\s.,]+)", texto)
    valores = set()
    for valor in padrao_valor:
        # Remove espaços e converte para o formato numérico
        valor_limpo = valor.replace(" ", "").replace(".", "").replace(",", ".")
        try:
            valores.add(float(valor_limpo))
        except ValueError:
            continue
    return valores

def encontrar_valor_comprovante(texto):
    """Busca valores monetários no comprovante (após 'VALOR DO PRINCIPAL')."""
    padrao_valor = re.findall(r"VALOR DO PRINCIPAL\s*R\$\s*([\d.,]+)", texto)
    valores = set()
    for valor in padrao_valor:
        # Remove "R$" e converte para o formato numérico
        valor_limpo = valor.replace("R$", "").replace(".", "").replace(",", ".")
        try:
            valores.add(float(valor_limpo))
        except ValueError:
            continue
    return valores

def organizar_por_nome_e_valor(arquivos):
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
        
        if "DARF" in nome:
            nome_fornecedor = encontrar_nome_fornecedor(texto_pdf, "DARF")
            valores = encontrar_valor_darf(texto_pdf)
            info_arquivos.append((arquivo, nome, valores, nome_fornecedor, "DARF"))
            st.write(f"📄 DARF: {nome} | Nome do Fornecedor: {nome_fornecedor} | Valores: {valores}")
        elif "Comprovante" in nome:
            nome_fornecedor = encontrar_nome_fornecedor(texto_pdf, "Comprovante")
            valores = encontrar_valor_comprovante(texto_pdf)
            info_arquivos.append((arquivo, nome, valores, nome_fornecedor, "Comprovante"))
            st.write(f"📄 Comprovante: {nome} | Nome do Fornecedor: {nome_fornecedor} | Valores: {valores}")
    
    # Associa DARFs e comprovantes
    for darf, nome_darf, valores_darf, nome_fornecedor_darf, tipo_darf in info_arquivos:
        if tipo_darf != "DARF":
            continue  # Ignora arquivos que não são DARFs
        
        # Primeira etapa: tenta agrupar apenas pelo valor
        correspondencia_encontrada = False
        for comprovante, nome_comp, valores_comp, nome_fornecedor_comp, tipo_comp in info_arquivos:
            if tipo_comp == "Comprovante" and valores_darf & valores_comp:
                agrupados[nome_darf] = [darf, comprovante]
                st.write(f"✅ Correspondência encontrada (VALOR): {nome_darf} ↔ {nome_comp}")
                correspondencia_encontrada = True
                break
        
        # Segunda etapa: se não encontrou correspondência pelo valor, tenta pelo nome + valor
        if not correspondencia_encontrada:
            for comprovante, nome_comp, valores_comp, nome_fornecedor_comp, tipo_comp in info_arquivos:
                if tipo_comp == "Comprovante" and nome_fornecedor_darf & nome_fornecedor_comp and valores_darf & valores_comp:
                    agrupados[nome_darf] = [darf, comprovante]
                    st.write(f"✅ Correspondência encontrada (NOME + VALOR): {nome_darf} ↔ {nome_comp}")
                    break
    
    # Gera PDFs agrupados e arquivo ZIP
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for nome_final, arquivos in agrupados.items():
            merger = PdfMerger()
            try:
                for doc in arquivos:
                    merger.append(doc)
                # Usa o nome do arquivo DARF como nome do arquivo final
                output_filename = nome_final
                output_path = os.path.join(temp_dir, output_filename)
                merger.write(output_path)
                merger.close()
                pdf_resultados[output_filename] = output_path
                zipf.write(output_path, arcname=output_filename)
                st.write(f"📂 Arquivo gerado: {output_filename}")
            except Exception as e:
                st.error(f"Erro ao juntar os arquivos {nome_final}: {str(e)}")
    
    return pdf_resultados, zip_path

def main():
    st.title("Agrupador de DARFs")
    
    # Adicionando um key único ao file_uploader
    arquivos = st.file_uploader("Envie seus arquivos", accept_multiple_files=True, key="file_uploader")
    
    if arquivos and len(arquivos) > 0:
        if st.button("🔗 Juntar e Processar PDFs", key="process_button"):
            pdf_resultados, zip_path = organizar_por_nome_e_valor(arquivos)
            
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
