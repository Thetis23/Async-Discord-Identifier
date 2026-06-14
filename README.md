# ⚡ Async Discord Identifier (v1.1)

An advanced, high-performance, and completely asynchronous Discord username availability checker built with Python. It utilizes Discord's modern `/pomelo` API endpoint to safely check 3-character, 4-character, or custom username lists without requiring any account authorization tokens.

## 🚀 Features
- **Asynchronous Engine:** Powered by `aiohttp` for multi-threaded, ultra-fast structural scanning.
- **Advanced Proxy Support:** Dynamically handles both HTTP and SOCKS5 proxies, automatically marking and isolating dead links.
- **Smart Rate-Limit Backoff:** Automatically parses Discord's `retry_after` response headers to cool down threads without crashing the process.
- **Webhook Integration:** Instantly broadcasts rich embed alerts straight to your configured Discord channel when an available username is caught.
- **Elegant Console UI:** Polished terminal feedback using `colorama` for beautiful real-time logging.

## ⚙️ Installation & Usage

1. Ensure you have Python installed on your system.
2. Open your system terminal and install the required dependencies:
   ```bash
   pip install aiohttp aiohttp-socks colorama
