import sys
from server.server_main import run_server
from client.client_main import run_client

def main():
    """The entry point of the script."""
    if "--server" in sys.argv:
        # ran by the server
        run_server()
    else:
        # ran by the client
        run_client()


if __name__ == "__main__":
    main()
