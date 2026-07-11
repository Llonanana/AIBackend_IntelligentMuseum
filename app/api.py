from flask import Blueprint, request, jsonify

from app.services.translate_service import Translate
from app.services.npc_service import ask_npc

import time

api = Blueprint('api', __name__)

# AI助理
@api.route('/generate', methods=['POST'])
def generate():
    """
    Endpoint to generate responses using the RAG model.
    Expects a JSON payload with a 'query' field.

    Stateless / single-turn: no conversation history. Use the socket.io
    "join" + "send_chat_message" events (see app/socket_events.py) for
    multi-turn chat with memory.
    """
    data = request.json
    query = data.get('query', '')
    lang = data.get('lang', 'en_US')
    personality = data.get("personality", "")

    if query.strip() == '':
        return jsonify({'error': 'Query field is required'})

    start_time = time.time()
    try:
        result = ask_npc(
            query=query,
            lang=lang,
            npc_role='博物館導覽員',
            personality=personality,
            is_rag=True,
        )
    except ValueError:
        return jsonify({'error': 'Invalid language code'})
    total_time = time.time() - start_time

    return jsonify({
        'parsed_query': result['parsed_query'],
        'response': result['response'],
        'metadata': result['metadata'],
        'RAG_response_time': total_time
    })


@api.route('/npc/ask', methods=['POST'])
def npc_ask():
    """
    Stateless / single-turn NPC query, kept for backward compatibility.
    Use the socket.io "join" + "send_chat_message" events for multi-turn
    chat with memory.
    """
    data = request.json
    query = data.get('query', '')
    lang = data.get('lang', 'en')
    npc_role = data.get('npc_role', '博物館導覽員')
    personality = data.get("personality", "")
    is_rag = data.get("is_rag", True)

    start_time = time.time()
    try:
        result = ask_npc(
            query=query,
            lang=lang,
            npc_role=npc_role,
            personality=personality,
            is_rag=is_rag,
        )
    except ValueError:
        return jsonify({
            'error': 'Error in your language code. Please use a valid language code.'
        })
    total_time = time.time() - start_time

    return jsonify({
        'parsed_query': result['parsed_query'],
        'response': result['response'],
        'metadata': result['metadata'],
        'RAG_response_time': total_time
    })


@api.route('/translate', methods=['POST'])
def translate():
    data = request.json
    text = data.get('text', '')
    target_language = data.get('target_language', 'en')

    # Set up translator
    translator = Translate()
    response = translator.translate(text, target_language)

    return jsonify(response)

########## ARCHIVED ##########
########## LangChain RAG ##########
# # Set up vector store
# loader = DirectoryLoader(path="assets", glob="./*.txt", loader_cls=TextLoader)
# text_splitter = RecursiveCharacterTextSplitter(chunk_size=1024, chunk_overlap=20)

# model_name = "sentence-transformers/all-MiniLM-L6-v2"
# model_kwargs = {'device': 'cpu'}
# embedding = HuggingFaceEmbeddings(
#     model_name=model_name,
#     model_kwargs=model_kwargs
# )

# persist_directory = 'chroma'

# store = VectorDB(loader, text_splitter, embedding, persist_directory)
# # vectordb = store.init_vectordb()
# vectordb = store.get_vectordb_from_disk()

# # Generate response
# rag = LangChainRAG(vectordb)
# response = rag.generate_response_with_retrieval(query)

# response = {
#     "query": response["query"],
#     "result": response["result"],
#     "source_documents": [doc.metadata["source"] for doc in response["source_documents"]],
#     "source_content": [doc.page_content for doc in response["source_documents"]]
# }
