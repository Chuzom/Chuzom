import sys, os, asyncio
sys.path.insert(0, sys.argv[1] + "/src")
os.environ["CHUZOM_HOME"] = sys.argv[2]
os.environ["HOME"] = sys.argv[2]
os.environ.pop("CHUZOM_SLIM", None)  # ensure unset -> default path

import chuzom.server as server  # this executes all the module-level registration code

async def main():
    tools = await server.mcp.list_tools()
    names = sorted(t.name for t in tools)
    print("REGISTERED_COUNT", len(names))
    for n in names:
        print("REG:", n)

asyncio.run(main())
