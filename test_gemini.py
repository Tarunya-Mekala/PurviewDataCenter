from app.ai.llm import llm_client


def main():
    response = llm_client.generate(
        prompt="""
        Explain what semantic column mapping means in one sentence.
        """
    )

    print("\nGemini response:")
    print(response)


if __name__ == "__main__":
    main()