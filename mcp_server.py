from mcp.server.fastmcp import FastMCP
from utils import read_prompt

mcp = FastMCP("DocumentMCP", log_level="ERROR")


docs = {
    "user-manual.pdf": "Complete user manual for the Nexus AI system, covering installation, configuration, and usage instructions.",
    "api-reference.md": "Technical API documentation including endpoints, authentication, and example requests for developers.",
    "troubleshooting-guide.docx": "Comprehensive troubleshooting guide covering common issues, error codes, and solutions.",
    "security-policy.pdf": "Security policies and best practices for protecting sensitive data and maintaining system integrity.",
    "release-notes.txt": "Latest release notes including new features, bug fixes, and breaking changes in version 2.1.0.",
    "integration-examples.md": "Code examples and tutorials for integrating Nexus with various platforms and frameworks.",
}


from pydantic import Field
from mcp.server.fastmcp.prompts import base


@mcp.tool(
    name="read_doc_contents",
    description="Read the contents of a document and return it as a string.",
)
def read_document(
    doc_id: str = Field(description="Id of the document to read"),
):
    if doc_id not in docs:
        raise ValueError(f"Doc with id {doc_id} not found")

    return docs[doc_id]


@mcp.tool(
    name="edit_document",
    description="Edit a document by replacing a string in the documents content with a new string",
)
def edit_document(
    doc_id: str = Field(description="Id of the document that will be edited"),
    old_str: str = Field(description="The text to replace. Must match exactly, including whitespace"),
    new_str: str = Field(description="The new text to insert in place of the old text"),
):
    if doc_id not in docs:
        raise ValueError(f"Doc with id {doc_id} not found")

    docs[doc_id] = docs[doc_id].replace(old_str, new_str)


@mcp.resource("docs://documents", mime_type="application/json")
def list_docs() -> list[str]:
    return list(docs.keys())


@mcp.resource("docs://documents/{doc_id}", mime_type="text/plain")
def fetch_doc(doc_id: str) -> str:
    if doc_id not in docs:
        raise ValueError(f"Doc with id {doc_id} not found")
    return docs[doc_id]


@mcp.prompt(
    name="format",
    description="Rewrites the contents of the document in Markdown format.",
)
def format_document(
    doc_id: str = Field(description="Id of the document to format"),
) -> list[base.Message]:
    # Read the prompt template from file
    prompt_template = read_prompt("format_document.txt")
    
    # Format the prompt with the document ID
    prompt = prompt_template.format(doc_id=doc_id)

    return [base.UserMessage(prompt)]


if __name__ == "__main__":
    mcp.run(transport="stdio")
