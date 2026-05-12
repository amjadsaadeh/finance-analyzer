from dotenv import load_dotenv

load_dotenv(override=False)

from app import demo


def main():
    demo.launch()


if __name__ == "__main__":
    main()
