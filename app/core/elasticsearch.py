from elasticsearch import Elasticsearch
from app.core.config import settings


def get_elasticsearch_client():
    """Get Elasticsearch client instance"""
    return Elasticsearch(
        [settings.ELASTICSEARCH_HOST],
        http_auth=(settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD),
        verify_certs=False,
        timeout=30
    )


es_client = get_elasticsearch_client()
