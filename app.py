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
        padrao_nome = re.findall(r"Parceiro\s*:\s*([\w\s]+?)\s*\d", texto)
    elif tipo_arquivo == "Comprovante":
        padrao_nome = re.findall(r"Nome\s*:\s*([\w\s]+?)\n", texto)
    else:
        return set()
    return set(padrao_nome)

def encontrar_valor_darf(texto):
    """Busca valores monetários no DARF mantendo as 3 tentativas originais"""
    valores = set()
    
    # 1ª Tentativa: Vl.Recolhe (formato tradicional)
    padrao_1 = re.findall(r"Vl\.Recolhe\s*:\s*([\d\s.,]+)", texto)
    for valor in padrao_1:
        valor_limpo = valor.replace(" ", "").replace(".", "").replace(",", ".")
        try:
            valores.add(float(valor_limpo))
        except ValueError:
            continue
    
    # 2ª Tentativa: VALOR DO PRINCIPAL (formato DARF)
    padrao_2 = re.findall(r"VALOR DO PRINCIPAL\s*R\$\s*([\d.,]+)", texto)
    for valor in padrao_2:
        valor_limpo = valor.replace(".", "").replace(",", ".")
        try:
            valores.add(float(valor_limpo))
        except ValueError:
            continue
    
    # 3ª Tentativa: Valor Total do Documento (formato multi-linha)
    padrao_3 = re.findall(r"Valor Total do Documento\s*\n\s*([\d\s.,]+)", texto)
    for valor in padrao_3:
        valor_limpo = valor.replace(" ", "").replace(".", "").replace(",", ".")
        try:
            valores.add(float(valor_limpo))
        except ValueError:
            continue
    
    return valores

def encontrar_valor_comprovante(texto):
    """Busca valores em comprovantes com tratamento preciso para todos os formatos"""
    valores = set()

    # --------------------------------------------------
    # CAMADA 1 - Padrão principal (VALOR DO PRINCIPAL)
    # Para: VALOR DO PRINCIPAL R$ 1.000,00 (formato BR)
    # --------------------------------------------------
    padrao1 = re.findall(r"VALOR DO PRINCIPAL\s*R\$\s*([\d\.,]+)", texto)
    for valor in padrao1:
        try:
            # Verifica se é formato BR (1.000,00) ou US (1,000.00)
            if ',' in valor and ('.' in valor and valor.index('.') < valor.index(',')):
                # Formato BR: 1.000,00 → remove pontos, troca vírgula
                valor_limpo = valor.replace('.', '').replace(',', '.')
            else:
                # Formato US: 1,000.00 → remove vírgulas
                valor_limpo = valor.replace(',', '')
            
            num = float(valor_limpo)
            valores.add(num)
        except ValueError:
            continue
    
    if valores:
        return valores

    # --------------------------------------------------
    # CAMADA 2 - Valores com decimais mal interpretados
    # Para casos como: 136.06406 (deveria ser 136064.06)
    # --------------------------------------------------
    padrao2 = re.findall(r"(?:VALOR TOTAL|Valor Total do Documento)\s*R?\$?\s*([\d\.,]+)", texto, re.IGNORECASE)
    for valor in padrao2:
        try:
            # Remove qualquer R$ e espaços
            valor_limpo = valor.replace('R$', '').replace(' ', '')
            
            # Verifica se tem separador decimal implícito (caso 136.06406)
            if '.' in valor_limpo and ',' not in valor_limpo:
                partes = valor_limpo.split('.')
                if len(partes[-1]) == 5:  # Padrão do erro (136.06406)
                    valor_limpo = valor_limpo.replace('.', '')
                elif len(partes[-1]) == 2:  # Formato normal (344.19)
                    pass  # Mantém como está
            elif ',' in valor_limpo:
                # Formato BR com vírgula decimal
                valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
            
            num = float(valor_limpo)
            valores.add(num)
        except ValueError:
            continue
    
    if valores:
        return valores

    # --------------------------------------------------
    # CAMADA 3 - Fallback para formatos complexos
    # --------------------------------------------------
    padrao3 = re.findall(r"(?:VALOR|Total|Valor)\s*:?\s*R?\$?\s*([\d\.,]+)", texto, re.IGNORECASE)
    for valor in padrao3:
        try:
            # Remove não-numéricos e trata decimais
            valor_limpo = valor.replace('R$', '').replace(' ', '')
            
            if '.' in valor_limpo and ',' in valor_limpo:
                # Decide qual é separador decimal
                if valor_limpo.index('.') > valor_limpo.index(','):  # 1.000,00
                    valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
                else:  # 1,000.00
                    valor_limpo = valor_limpo.replace(',', '')
            elif ',' in valor_limpo:  # 100,00
                valor_limpo = valor_limpo.replace(',', '.')
            
            num = float(valor_limpo)
            valores.add(num)
        except ValueError:
            continue

    return valores

def organizar_por_nome_e_valor(arquivos):
    st.write("### Processando arquivos...")
    temp_dir = tempfile.mkdtemp()
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
            continue
        
        correspondencia_encontrada = False
        for comprovante, nome_comp, valores_comp, nome_fornecedor_comp, tipo_comp in info_arquivos:
            if tipo_comp == "Comprovante" and nome_fornecedor_darf & nome_fornecedor_comp and valores_darf & valores_comp:
                agrupados[nome_darf] = [darf, comprovante]
                st.write(f"✅ Correspondência encontrada (NOME + VALOR): {nome_darf} ↔ {nome_comp}")
                correspondencia_encontrada = True
                break
        
        if not correspondencia_encontrada:
            for comprovante, nome_comp, valores_comp, nome_fornecedor_comp, tipo_comp in info_arquivos:
                if tipo_comp == "Comprovante" and valores_darf & valores_comp:
                    agrupados[nome_darf] = [darf, comprovante]
                    st.write(f"✅ Correspondência encontrada (VALOR): {nome_darf} ↔ {nome_comp}")
                    break
    
    # Gera PDFs agrupados e arquivo ZIP
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_zip:
        zip_path = tmp_zip.name
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for nome_final, arquivos in agrupados.items():
                merger = PdfMerger()
                try:
                    for doc in arquivos:
                        merger.append(doc)
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
    st.title("Agrupador de DARFs e Comprovantes")
    
    arquivos = st.file_uploader("Selecione os arquivos DARF e comprovantes", 
                              accept_multiple_files=True, 
                              type=["pdf"])
    
    if arquivos and len(arquivos) > 0:
        if st.button("🔗 Processar Documentos"):
            st.write("### Iniciando processamento...")
            pdf_resultados, zip_path = organizar_por_nome_e_valor(arquivos)
            
            if os.path.exists(zip_path):
                for nome, caminho in pdf_resultados.items():
                    with open(caminho, "rb") as f:
                        st.download_button(
                            label=f"📄 Baixar {nome}",
                            data=f,
                            file_name=nome,
                            mime="application/pdf",
                            key=f"download_{nome}"
                        )
                
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="📥 Baixar todos como ZIP",
                        data=f,
                        file_name="documentos_agrupados.zip",
                        mime="application/zip",
                        key="download_zip"
                    )
            else:
                st.error("Erro ao gerar o arquivo ZIP.")

if __name__ == "__main__":
    main()
