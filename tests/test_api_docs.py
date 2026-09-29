import pytest

DOC_PATHS = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/swagger",
    "/swagger-ui",
    "/api-docs",
    "/q/openapi",
    "/graphql",
]


@pytest.mark.parametrize("path", DOC_PATHS)
def test_api_docs_are_not_served(client, path):
    assert client.get(path).status_code == 404
