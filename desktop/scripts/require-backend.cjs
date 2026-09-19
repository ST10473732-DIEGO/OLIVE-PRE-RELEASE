const fs = require("node:fs");
const path = require("node:path");
module.exports = async (context) => {
  if (
    !fs.existsSync(
      path.join(context.packager.projectDir, "backend-artifact", "python.exe"),
    )
  ) {
    throw new Error(
      "Packaging requires a validated self-contained backend-artifact/python.exe and Python dependencies. M1 uses the repository virtual environment; it is not a distributable build.",
    );
  }
};
