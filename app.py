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
    """Busca valores monetários no DARF."""
    valores = set()
    
    # Primeira tentativa: valor após "Vl.Recolhe :"
    padrao_valor_1 = re.findall(r"Vl\.Recolhe\s*:\s*([\d\s.,]+)", texto)
    for valor in padrao_valor_1:
        # Remove espaços e converte para o formato numérico (ponto como separador decimal)
        valor_limpo = valor.replace(" ", "").replace(".", "").replace(",", ".")
        try:
            valores.add(float(valor_limpo))
        except ValueError:
            continue
    
    # Segunda tentativa: valor após "VALOR DO PRINCIPAL"
    padrao_valor_2 = re.findall(r"VALOR DO PRINCIPAL\s*R\$\s*([\d.,]+)", texto)
    for valor in padrao_valor_2:
        # Remove "R$" e converte para o formato numérico (ponto como separador decimal)
        valor_limpo = valor.replace("R$", "").replace(".", "").replace(",", ".")
        try:
            valores.add(float(valor_limpo))
        except ValueError:
            continue
    
    # Terceira tentativa: valor na linha seguinte a "Valor Total do Documento"
    padrao_valor_3 = re.findall(r"Valor Total do Documento\s*\n\s*([\d\s.,]+)", texto)
    for valor in padrao_valor_3:
        # Remove espaços e separadores de milhares, mantendo o ponto decimal
        valor_limpo = valor.replace(" ", "").replace(",", "")
        try:
            valores.add(float(valor_limpo))
        except ValueError:
            continue
    
    return valores

def encontrar_valor_comprovante(texto):
    """Busca valores com 2 tentativas: padrão original + milhões"""
    valores = set()
    
    # --------------------------------------------------
    # TENTATIVA 1: CÓDIGO ORIGINAL (funciona para 99% dos casos)
    # --------------------------------------------------
    padrao_original = re.findall(r"VALOR DO PRINCIPAL\s*R\$\s*([\d\.,]+)", texto)
    for valor in padrao_original:
        try:
            # Formato original (funciona para valores até 999.999,99)
            valor_limpo = valor.replace(".", "").replace(",", ".")
            num = float(valor_limpo)
            valores.add(num)
        except ValueError:
            continue
    
    if valores:  # Se encontrou valores com a primeira lógica, retorna
        return valores
    
    # --------------------------------------------------
    # TENTATIVA 2: LÓGICA PARA MILHÕES (apenas se a primeira falhar)
    # --------------------------------------------------
    padroes_especiais = [
        r"VALOR (?:DO PRINCIPAL|TOTAL)\s*R\$\s*([\d\.,]+)",
        r"Valor\s*:\s*R\$\s*([\d\.,]+)",
        r"Total\s*a\s*Pagar\s*R\$\s*([\d\.,]+)"
    ]
    
    for padrao in padroes_especiais:
        for valor in re.findall(padrao, texto):
            try:
                # Remove R$ e espaços
                valor_limpo = valor.replace("R$", "").strip()
                
                # Lógica inteligente para milhões
                if ',' in valor_limpo and '.' in valor_limpo:
                    if valor_limpo.index(',') < valor_limpo.index('.'):  # Formato "2,758,525.77"
                        valor_limpo = valor_limpo.replace(',', '')
                    else:  # Formato "2.758.525,77"
                        valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
                elif ',' in valor_limpo:  # Formato "2758525,77"
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
            continue  # Ignora arquivos que não são DARFs
        
        # Primeira etapa: tenta agrupar por NOME + VALOR
        correspondencia_encontrada = False
        for comprovante, nome_comp, valores_comp, nome_fornecedor_comp, tipo_comp in info_arquivos:
            if tipo_comp == "Comprovante" and nome_fornecedor_darf & nome_fornecedor_comp and valores_darf & valores_comp:
                agrupados[nome_darf] = [darf, comprovante]
                st.write(f"✅ Correspondência encontrada (NOME + VALOR): {nome_darf} ↔ {nome_comp}")
                correspondencia_encontrada = True
                break
        
        # Segunda etapa: se não encontrou correspondência por NOME + VALOR, tenta apenas pelo VALOR
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
    st.title("Agrupador de DARFs")  # Nome do app alterado
    
    # Texto do botão de upload personalizado
    arquivos = st.file_uploader("Selecione os arquivos DARF e comprovantes", accept_multiple_files=True, key="file_uploader")
    
    if arquivos and len(arquivos) > 0:
        # Texto do botão de processamento personalizado
        if st.button("🔗 Processar Documentos", key="process_button"):
            st.write("### Iniciando processamento...")  # Mensagem personalizada
            pdf_resultados, zip_path = organizar_por_nome_e_valor(arquivos)
            
            # Verifica se o arquivo ZIP foi gerado corretamente
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
                
                # Força o download do ZIP
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="📥 Baixar todos como ZIP",
                        data=f,
                        file_name="documentos_agrupados.zip",  # Nome do ZIP personalizado
                        mime="application/zip",
                        key="download_zip"
                    )
            else:
                st.error("Erro ao gerar o arquivo ZIP. Verifique os logs para mais detalhes.")

if __name__ == "__main__":
    main()        
