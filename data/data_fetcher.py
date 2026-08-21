# src/data/data_fetcher.py

def get_client():
    # Agregamos la configuración de proxy a requests_params
    proxies = {
        'http': config.PROXY_URL,   # O directamente el string de tu proxy
        'https': config.PROXY_URL
    }

    client = Client(
        config.BINANCE_API_KEY,
        config.BINANCE_API_SECRET,
        requests_params={
            "timeout": 10,
            "proxies": proxies  # <--- Esto redirige el ping fuera de EE. UU.
        }
    )
    return client
