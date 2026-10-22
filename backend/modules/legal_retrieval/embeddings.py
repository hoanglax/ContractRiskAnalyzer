from functools import lru_cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "intfloat/multilingual-e5-base"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed_passages(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()

    prepared = [f"passage: {text}" for text in texts]

    vectors = model.encode(
        prepared,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    model = get_embedding_model()

    vector = model.encode(
        f"query: {text}",
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    return vector.tolist()