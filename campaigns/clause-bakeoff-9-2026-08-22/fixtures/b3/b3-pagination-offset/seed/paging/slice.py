"""Slice a list into 1-based pages."""


def page_slice(items, page, per_page):
    """Return the items on `page`, counting from page 1.

    Page 1 holds the first `per_page` items, page 2 the next `per_page`, and so
    on. A page past the end of the list is empty, and a partial last page holds
    whatever remains.
    """
    start = page * per_page
    return items[start:start + per_page]
