"""Fixed read-only DOM extraction. No caller can supply browser-side code."""

ACCESSIBLE_NAME = r"""element => {
    const labelled = (element.getAttribute('aria-labelledby') || '').split(/\s+/).slice(0, 8)
        .map(id => element.ownerDocument.getElementById(id)?.textContent || '').join(' ').trim();
    const labels = Array.from(element.labels || []).slice(0, 8).map(label => label.textContent || '').join(' ').trim();
    return (element.getAttribute('aria-label') || labelled || labels || element.getAttribute('placeholder') ||
        element.getAttribute('title') || element.textContent || element.getAttribute('name') || '').trim().slice(0, 300);
}"""


async def accessible_name(element):
    return await element.evaluate(ACCESSIBLE_NAME)
