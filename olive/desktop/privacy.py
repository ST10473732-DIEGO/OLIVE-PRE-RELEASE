"""Conservative secret-field detection for generic accessible controls."""


def search_field(control):
    """A destination containing 'search' does not make its message editor a search box."""
    import re
    return (control.get("control_type") == "Edit" and not control.get("password")
            and bool(re.match(r"\s*search\b", control.get("name", ""), re.IGNORECASE)))

def secret_field(name="", input_type="", autocomplete="", password=False):
    label = str(name).casefold().replace("_", " ").replace("-", " ")
    return bool(password or input_type == "password" or autocomplete in {"current-password", "new-password", "one-time-code"}
                or any(token in label for token in ("password", "passphrase", "seed phrase", "private key", "recovery code", "one time code", "security code")))
