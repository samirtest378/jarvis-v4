import httpx
import pytest

from web_reader import WebReadError, read_public_webpage


async def public_resolver(_hostname: str) -> list[str]:
    return ["93.184.216.34"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "https://user:password@example.com/",
        "https://example.com:8443/",
        "https://localhost/",
        "https://127.0.0.1/",
        "https://10.0.0.4/",
    ],
)
async def test_rejects_unsafe_targets(url):
    async def resolver(hostname: str) -> list[str]:
        return [hostname] if hostname.replace(".", "").isdigit() else ["127.0.0.1"]

    with pytest.raises(WebReadError):
        await read_public_webpage(url, resolver=resolver)


@pytest.mark.asyncio
async def test_reads_html_without_active_or_form_content():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="""
                <html><head><title>Safe page</title><script>steal()</script></head>
                <body><main><h1>Public information</h1><p>The useful answer.</p></main>
                <form>Secret form text<input value='private'></form><style>hidden</style></body></html>
            """,
        )

    page = await read_public_webpage(
        "https://example.com/article#section",
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    assert page.url == "https://example.com/article"
    assert page.title == "Safe page"
    assert "Public information" in page.text
    assert "The useful answer." in page.text
    assert "steal" not in page.text
    assert "Secret form" not in page.text
    assert seen[0].method == "GET"
    assert "authorization" not in seen[0].headers
    assert "cookie" not in seen[0].headers


@pytest.mark.asyncio
async def test_revalidates_redirect_and_blocks_private_destination():
    async def resolver(hostname: str) -> list[str]:
        return ["127.0.0.1"] if hostname == "private.example" else ["93.184.216.34"]

    transport = httpx.MockTransport(
        lambda _request: httpx.Response(302, headers={"location": "https://private.example/admin"})
    )
    with pytest.raises(WebReadError, match="private"):
        await read_public_webpage(
            "https://example.com/",
            resolver=resolver,
            transport=transport,
        )


@pytest.mark.asyncio
async def test_rejects_large_or_binary_responses():
    large = httpx.MockTransport(
        lambda _request: httpx.Response(200, headers={"content-type": "text/plain"}, content=b"x" * (1024 * 1024 + 1))
    )
    with pytest.raises(WebReadError, match="too large"):
        await read_public_webpage("https://example.com/", resolver=public_resolver, transport=large)

    binary = httpx.MockTransport(
        lambda _request: httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=b"bin")
    )
    with pytest.raises(WebReadError, match="readable text"):
        await read_public_webpage("https://example.com/", resolver=public_resolver, transport=binary)
