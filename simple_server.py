#!/usr/bin/env python3
"""CSP 헤더를 포함한 간단한 HTTP 서버."""

import http.server
import socketserver
from http.server import SimpleHTTPRequestHandler

class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # CORS 헤더 추가
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

        # CSP 헤더를 완전히 관대하게 설정 (eval 허용)
        self.send_header('Content-Security-Policy',
                        "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                        "script-src * 'unsafe-inline' 'unsafe-eval'; "
                        "style-src * 'unsafe-inline' 'unsafe-eval'; "
                        "font-src * data:; "
                        "img-src * data: blob:; "
                        "connect-src * ws: wss:; "
                        "object-src 'none'; "
                        "base-uri 'self';")

        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    PORT = 9000

    with socketserver.TCPServer(("", PORT), CustomHTTPRequestHandler) as httpd:
        print(f"🚀 대시보드 서버가 포트 {PORT}에서 시작되었습니다.")
        print(f"📱 웹 브라우저에서 접속: http://localhost:{PORT}/dashboard.html")
        print("⏹️  서버 종료: Ctrl+C")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 서버가 종료되었습니다.")