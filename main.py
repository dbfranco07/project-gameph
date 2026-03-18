import sys


def main():
    if "--server" in sys.argv:
        from server.server_main import run_server

        run_server()
    else:
        from client.client_main import run_client

        run_client()


if __name__ == "__main__":
    main()
