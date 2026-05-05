from langchain.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.embeddings import OpenAIEmbeddings

def build_retriever(file_path):
    loader = TextLoader(file_path, encoding='utf-8')
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = splitter.split_documents(documents)

    db = FAISS.from_documents(docs, OpenAIEmbeddings())
    return db.as_retriever()