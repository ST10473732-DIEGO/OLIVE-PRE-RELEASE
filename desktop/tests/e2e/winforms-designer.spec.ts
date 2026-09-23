import {test, expect, _electron as electron} from "@playwright/test";
import {mkdtemp, mkdir, readFile, writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import path from "node:path";
import {spawn} from "node:child_process";
import {openSpace} from "./shell";
import {captureMail} from "./m4-capture";

test("real WinForms calculator through drag design, C# events, reopen, native run and conflict", async () => {
  test.skip(process.platform!=='win32','Native Windows Forms execution/designer requires Windows; retained native Windows journey');
  test.setTimeout(240000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-designer-"));
  const projects = path.join(profile, "projects"); await mkdir(projects);
  const evidence = path.resolve("../artifacts/core/functionality/designer"); await mkdir(evidence, {recursive: true});
  const app = await electron.launch({args: [path.resolve(".")], env: {...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1"}});
  let workspace = "";
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", {name: "Enter OLIVE", exact: true}).click();
    await openSpace(page, "Studio");
    await page.getByRole("button", {name: "New project", exact: true}).first().click();
    await expect(page.locator('.language-card[data-language="csharp"]')).toBeEnabled({timeout: 90000});
    await page.locator('.language-card[data-language="csharp"]').click();
    await page.getByRole("radio", {name: /Windows Forms visual application/}).click();
    await page.getByLabel("Project name", {exact: true}).fill("Calculator");
    await page.getByLabel("Project location", {exact: true}).fill(projects);
    await page.getByRole("button", {name: "Create project", exact: true}).click();
    await expect(page.locator(".wizard-done")).toContainText("Created", {timeout: 90000});
    await page.getByRole("dialog", {name: "New project"}).getByRole("button", {name: "Close", exact: true}).click();
    await page.getByRole("button", {name: "Design form", exact: true}).click();
    const designer = page.getByRole("dialog", {name: "Windows Forms designer"});
    await designer.getByLabel("Form title", {exact: true}).fill("OLIVE Designer Calculator Fixture");
    const canvas = designer.getByLabel("Form canvas", {exact: true});
    const toolbox = designer.getByRole("complementary", {name: "Control toolbox"});
    const add = async (type: string, name: string, text: string, x: number, y: number) => {
      await toolbox.getByRole("button", {name: type, exact: true}).dragTo(canvas, {targetPosition: {x, y}});
      await designer.getByLabel("Control name", {exact: true}).fill(name);
      await designer.getByLabel("Control text", {exact: true}).fill(text);
      await designer.getByLabel("Control x", {exact: true}).fill(String(x));
      await designer.getByLabel("Control y", {exact: true}).fill(String(y));
    };
    await add("TextBox", "leftInput", "2", 24, 40);
    await add("TextBox", "rightInput", "3", 184, 40);
    await add("ComboBox", "operationBox", "+", 344, 40);
    await designer.getByLabel("ComboBox items", {exact: true}).fill("+\n-\n*\n/");
    await add("Label", "resultLabel", "Ready", 24, 152);
    await designer.getByLabel("Control width", {exact: true}).fill("400");
    await add("Button", "calculateButton", "Calculate", 24, 96);
    const button = canvas.getByRole('button', {name: 'Button calculateButton', exact: true});
    const box = (await button.boundingBox())!;
    await page.mouse.move(box.x + 30, box.y + 15); await page.mouse.down();
    await page.mouse.move(box.x + 46, box.y + 31); await page.mouse.up();
    await expect(designer.getByLabel('Control x', {exact: true})).toHaveValue('40');
    await expect(designer.getByLabel('Control y', {exact: true})).toHaveValue('112');
    await designer.getByRole('button', {name: 'Undo design', exact: true}).click();
    const corner = (await designer.getByLabel('Resize calculateButton', {exact: true}).boundingBox())!;
    await page.mouse.move(corner.x + 5, corner.y + 5); await page.mouse.down();
    await page.mouse.move(corner.x + 21, corner.y + 21); await page.mouse.up();
    await expect(designer.getByLabel('Control width', {exact: true})).toHaveValue('136');
    await designer.getByRole('button', {name: 'Undo design', exact: true}).click();
    await canvas.getByRole('button', {name: 'TextBox rightInput', exact: true}).click({modifiers: ['Shift']});
    await toolbox.getByRole('button', {name: 'Align left', exact: true}).click();
    await expect(canvas.getByRole('button', {name: 'TextBox rightInput', exact: true})).toHaveCSS('left', '24px');
    await designer.getByRole('button', {name: 'Undo design', exact: true}).click();
    await toolbox.getByRole('button', {name: 'calculateButton', exact: true}).click();
    await designer.getByLabel("Control text", {exact: true}).fill("Temporary text");
    await designer.getByRole("button", {name: "Undo design", exact: true}).click();
    await expect(designer.getByLabel("Control text", {exact: true})).toHaveValue("Calculate");
    await designer.getByRole("button", {name: "Redo design", exact: true}).click();
    await expect(designer.getByLabel("Control text", {exact: true})).toHaveValue("Temporary text");
    await designer.getByRole("button", {name: "Undo design", exact: true}).click();
    await designer.getByLabel("Event handler", {exact: true}).fill("Calculate_Click");
    await designer.getByRole("button", {name: "Edit event code", exact: true}).click();
    const editor = page.getByRole("textbox", {name: "Source editor"});
    await expect(editor).toBeVisible();
    const eventCode = `namespace OliveDesigned;
public partial class MainForm
{
    private void Calculate_Click(object? sender, System.EventArgs e)
    {
        if (!double.TryParse(leftInput.Text, out var left) || !double.TryParse(rightInput.Text, out var right))
        { resultLabel.Text = "Invalid number"; return; }
        if (operationBox.Text == "/" && right == 0)
        { resultLabel.Text = "Cannot divide by zero"; return; }
        double value = operationBox.Text switch { "+" => left + right, "-" => left - right, "*" => left * right, "/" => left / right, _ => double.NaN };
        resultLabel.Text = value.ToString(System.Globalization.CultureInfo.InvariantCulture);
    }
}
`;
    await editor.press("Control+A"); await page.keyboard.insertText(eventCode);
    await page.getByRole("button", {name: "Save", exact: true}).click();
    const eventPath = path.join(projects, "Calculator/Events/Calculate_Click.cs");
    // Input.insertText follows Monaco's typing/indentation path, unlike a native
    // clipboard paste. Verify every source line, then preserve the actual bytes.
    const normalize = (value: string) => value.split("\n").map(line => line.trim()).join("\n").trim();
    await expect.poll(async () => normalize(await readFile(eventPath, "utf8"))).toBe(normalize(eventCode));
    const savedEventCode = await readFile(eventPath, "utf8");
    await page.getByRole("button", {name: "Design form", exact: true}).click();
    await expect(designer.getByLabel("Form title", {exact: true})).toHaveValue("OLIVE Designer Calculator Fixture");
    await expect(canvas.locator(".wf-control")).toHaveCount(5);
    await designer.getByRole("button", {name: "Preview", exact: true}).click();
    await captureMail(page, app, path.join(evidence, "design-preview.png"));
    await designer.getByRole("button", {name: "Build and run native app", exact: true}).click();
    const snapshot = () => page.evaluate(() => window.olive.call("runtime.snapshot", {})) as Promise<{workspaces: {id: string; root_path: string}[]; runs: {id: string; workspace_id: string; state: string; process_id: number; application_type: string}[]}>;
    let pid = 0;
    await expect.poll(async () => {const s = await snapshot(); workspace = s.workspaces.find(w => w.root_path.toLowerCase() === path.join(projects, "Calculator").toLowerCase())!.id; const run = s.runs.find(r => r.workspace_id === workspace && r.application_type === "dotnet_application" && r.state === "running"); pid = run?.process_id || 0; return pid;}, {timeout: 30000}).toBeGreaterThan(0);
    const probe = spawn(path.resolve("../.venv/Scripts/python.exe"), [path.resolve("../scripts/winforms_fixture_probe.py"), "--workspace", path.join(projects, "Calculator"), "--pid", String(pid), "--output", path.join(evidence, "native-result.json")], {windowsHide: true});
    let log = ""; probe.stdout.on("data", value => {log += value;}); probe.stderr.on("data", value => {log += value;});
    await expect.poll(() => probe.exitCode, {timeout: 70000, message: "The exact native calculator probe must finish"}).not.toBeNull();
    expect(probe.exitCode, log).toBe(0);
    expect(log).toContain('"verified": true');
    await expect.poll(async () => (await snapshot()).runs.some(r => r.workspace_id === workspace && r.state === "running"), {timeout: 15000}).toBe(false);
    expect(await readFile(eventPath, "utf8")).toBe(savedEventCode);
    const generated = path.join(projects, "Calculator/MainForm.Designer.cs");
    const original = await readFile(generated, "utf8");
    await writeFile(generated, original + "// external fixture divergence\n");
    await page.getByRole("button", {name: "Design form", exact: true}).click();
    await expect(designer.getByRole("alert")).toContainText("Generated code changed outside Design");
    await expect(designer.getByRole("button", {name: "Save design", exact: true})).toBeDisabled();
    await app.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows()[0].setSize(1024, 720));
    await captureMail(page, app, path.join(evidence, "conflict-small.png"));
    expect(await readFile(generated, "utf8")).toBe(original + "// external fixture divergence\n");
    expect(await readFile(eventPath, "utf8")).toBe(savedEventCode);
  } finally {await app.close();}
});

test('Linux does not advertise native Windows Forms creation',async()=>{
  test.skip(process.platform!=='linux','Linux platform truthfulness');
  const profile=await mkdtemp(path.join(tmpdir(),'olive-winforms-unavailable-'));
  const app=await electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  try{
    const page=await app.firstWindow();
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await openSpace(page,'Studio');
    await page.getByRole('button',{name:'New project',exact:true}).first().click();
    await expect(page.locator('.language-card[data-language="csharp"]')).toBeEnabled({timeout:90000});
    await page.locator('.language-card[data-language="csharp"]').click();
    await expect(page.getByRole('radio',{name:/Windows Forms visual application/})).toHaveCount(0);
    await expect(page.getByRole('radio',{name:/Console application/})).toBeVisible();
  }finally{await app.close();}
});
