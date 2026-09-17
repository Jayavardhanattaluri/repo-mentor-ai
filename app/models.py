from pydantic import BaseModel, Field


class IssueLabel(BaseModel):
    name: str


class Issue(BaseModel):
    number: int
    title: str
    body: str = ""
    html_url: str
    state: str
    labels: list[IssueLabel] = Field(default_factory=list)
    assignees: list[dict] = Field(default_factory=list)


class IssueScore(BaseModel):
    issue_number: int
    score: int
    reasons: list[str]


class TestResult(BaseModel):
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    passed: bool