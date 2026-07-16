from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
import ssl
import json

DIFY_URL = "https://dify.aicareu.com/v1/chat-messages"

class ProxyHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        auth = self.headers.get("Authorization", "")

        print(f"收到请求，body长度: {length}")
        print(f"Authorization: {auth[:20]}...")
        print(f"Body: {body[:200]}")

        # 忽略 SSL 证书验证
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            DIFY_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": auth,
                "Accept": "application/json",
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, context=ctx) as res:
                content_type = res.headers.get("Content-Type", "application/json")
                print(f"Dify 返回成功，Content-Type: {content_type}")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                # 逐块转发，不等待完整响应，这样前端可以边收边显示（SSE 流式）
                while True:
                    chunk = res.read(512)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()

        except urllib.error.HTTPError as e:
            error_body = e.read()
            print(f"HTTP错误 {e.code}: {error_body}")
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_body)

        except Exception as e:
            print(f"其他错误: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        print(format % args)

print("代理服务器启动：http://localhost:9090")
HTTPServer(("", 9090), ProxyHandler).serve_forever()