from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Every list endpoint is paginated (CLAUDE.md)."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
