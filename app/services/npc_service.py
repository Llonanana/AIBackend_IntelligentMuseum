import json
import threading

from app.services.translate_service import Translate
from rag.llama_index import LLaMAIndexRAG

_engine = None
_engine_lock = threading.Lock()


def _get_engine():
    """LLaMAIndexRAG rebuilds its Weaviate index on every __init__, so it must
    be shared across requests rather than instantiated per call."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = LLaMAIndexRAG()
    return _engine


def get_role_features(npc_role):
    with open('npc_role_config.json', 'r', encoding='utf-8') as f:
        roles_config = json.load(f)
    return roles_config.get(npc_role, {})


def ask_npc(query, lang, npc_role, personality, is_rag, history=None):
    """Translate query, build the NPC prompt (with optional conversation
    history) and run it through the shared RAG engine.

    `history` is a list of {"role": "user"|"npc", "sender": str, "content": str}
    dicts, oldest first, not including the current `query`.
    """
    translator = Translate()
    chi_query = translator.translate(query, "zh_TW")

    lang_chinese_name = translator.get_language_name_in_chinese(lang)
    if lang_chinese_name is None:
        raise ValueError('Invalid language code')

    role_features = get_role_features(npc_role)
    dynasty = role_features.get("dynasty", "現代")
    background = role_features.get("background", "")
    tone = role_features.get("tone", "中立")
    style = role_features.get("style", "正常")

    if npc_role != "博物館導覽員":
        chi_query = f"({npc_role}-{dynasty})" + chi_query

    query_info = {
        'query': chi_query,
        'target_lang_code': lang,
        'target_lang': lang_chinese_name,
        'npc_role': npc_role,
        'dynasty': dynasty,
        'background': background,
        'tone': tone,
        'style': style,
        'personality': personality,
        'is_rag': is_rag,
        'history': history or [],
    }

    engine = _get_engine()
    # generate_response_with_retrieval mutates the shared query engine's prompt
    # templates before using them, so concurrent calls must be serialized.
    with _engine_lock:
        response = engine.generate_response_with_retrieval(query_info)

    return {
        'parsed_query': chi_query,
        'response': response.get('response', ''),
        'metadata': response.get('metadata', {}),
    }
