import logging
from langchain_community.tools.file_management import (
    WriteFileTool,
    ReadFileTool,
    ListDirectoryTool,
)
from .decorators import create_logged_tool

logger = logging.getLogger(__name__)

# Initialize file management tools with logging
LoggedWriteFile = create_logged_tool(WriteFileTool)
write_file_tool = LoggedWriteFile()

LoggedReadFile = create_logged_tool(ReadFileTool)
read_file_tool = LoggedReadFile()

LoggedListDirectory = create_logged_tool(ListDirectoryTool)
list_files_tool = LoggedListDirectory()
