import { test, expect } from "@playwright/test";

test("world inspection, play/pause, rewind, branch and synchronized comparison", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const original = await (
    await request.post("/api/runs", {
      data: { name: "Browser QA colony", config: { population: 8, seed: 88 } },
    })
  ).json();
  await request.post(`/api/runs/${original.id}/advance`, {
    data: { days: 12 },
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A small world." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Browser QA colony", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("EXPLORE THE COLONY", { exact: true })
    .selectOption("3");
  await expect(
    page.getByRole("heading", { name: "Theo", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Step one day" }).click();
  await expect(
    page.getByRole("img", { name: /Island at day 13/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Play simulation" }).click();
  await expect(
    page.getByRole("button", { name: "Pause simulation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pause simulation" }).click();
  await page.getByLabel("Replay day").fill("6");
  await expect(
    page.getByRole("img", { name: /Island at day 6/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Branch here" }).click();
  await page
    .getByLabel("Colony name", { exact: true })
    .fill("Browser QA branch");
  await page
    .getByRole("combobox", { name: "Sharing rule", exact: true })
    .selectOption("pool");
  await page.getByLabel("External food grant").fill("5");
  await page.getByRole("button", { name: "Create this future" }).click();
  await expect(
    page.getByRole("heading", { name: "Browser QA branch", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Compare saved colony").selectOption(original.id);
  await expect(page.getByRole("img", { name: /Island at day 6/ })).toHaveCount(
    2,
  );
  await page.getByLabel("Replay day").fill("4");
  await expect(page.getByRole("img", { name: /Island at day 4/ })).toHaveCount(
    2,
  );
  await page.getByRole("button", { name: "Close comparison" }).click();
  await page.getByRole("button", { name: "World configuration" }).click();
  await expect(page.getByRole("dialog")).toContainText("daily yield");
  await page.getByRole("button", { name: "Close dialog" }).click();
  const after = await (
    await request.get(`/api/runs/${original.id}/state?day=6`)
  ).json();
  expect(after.totals.grants).toBe(0);
  expect(errors).toEqual([]);
});

test("lab batch, results, exports and replay", async ({ page, request }) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Experiment lab", exact: true })
    .click();
  await page.getByLabel("Matched seeds").fill("2");
  await page.getByLabel("Days per world").fill("30");
  await page
    .getByRole("button", { name: "Run experiment", exact: true })
    .click();
  await expect(page.getByText("COMPLETE", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByRole("heading", { name: /12 \/ 12 worlds explored/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Paired differences" }),
  ).toBeVisible();
  const csv = page.getByRole("link", { name: "CSV", exact: true });
  const href = await csv.getAttribute("href");
  const response = await request.get(href!);
  expect(response.ok()).toBeTruthy();
  expect(await response.text()).toContain("run_id,seed,condition");
  const zip = await request.get(href!.replace("format=csv", "format=zip"));
  expect(zip.headers()["content-type"]).toBe("application/zip");
  await page.getByRole("button", { name: /Replay individual \/ pool/ }).click();
  await expect(
    page.getByRole("img", { name: /Island at day 30/ }),
  ).toBeVisible();
});

test("research degrades gracefully without a local model and mobile layout fits", async ({
  page,
}) => {
  await page.route("**/api/models", (r) =>
    r.fulfill({
      json: {
        available: false,
        models: [],
        error: "Ollama unavailable. World and Lab remain available.",
      },
    }),
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Research journal", exact: true })
    .click();
  await expect(page.getByText("Local model not connected")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Begin research" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("heading", { name: "Work with Codex instead" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "The island", exact: true }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

test("saved worlds can be reopened through the library", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("img", { name: /Island at day/ })).toBeVisible();
  await page.getByRole("button", { name: "Saved worlds", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Saved worlds" });
  await expect(dialog).toBeVisible();
  await dialog.locator(".saved-worlds button").first().click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("img", { name: /Island at day/ })).toBeVisible();
});

test("research streams output, preserves transcript on reload, and exposes prompts", async ({
  page,
}) => {
  const session = {
    id: "live-test",
    kind: "research",
    created: Date.now() / 1000,
    status: "running",
    spec: { question: "Does sharing help?", model: "test" },
    data: { rounds: [], started_at: Date.now() / 1000 },
  };
  let poll = 0;
  const events = [
    {
      seq: 1,
      job: session.id,
      created: session.created,
      kind: "model.request",
      message: "Asking the model for an experiment proposal",
      data: {
        request_id: "call1",
        attempt: 1,
        request: {
          messages: [{ role: "user", content: "Exact research prompt" }],
          stream: true,
        },
      },
    },
    {
      seq: 2,
      job: session.id,
      created: session.created,
      kind: "model.delta",
      message: "Model output",
      data: {
        request_id: "call1",
        channel: "content",
        text: "First streamed fragment",
      },
    },
    {
      seq: 3,
      job: session.id,
      created: session.created,
      kind: "model.delta",
      message: "Model output",
      data: {
        request_id: "call1",
        channel: "content",
        text: " plus the next fragment",
      },
    },
  ];
  await page.route("**/api/research", (route) =>
    route.fulfill({ json: [session] }),
  );
  await page.route("**/api/research/live-test/events?*", (route) => {
    const after = Number(
      new URL(route.request().url()).searchParams.get("after"),
    );
    const available = events
      .slice(0, ++poll === 1 ? 2 : 3)
      .filter((e) => e.seq > after);
    return route.fulfill({
      json: {
        events: available,
        next_cursor: available.at(-1)?.seq || after,
        has_more: false,
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Research/ }).click();
  const output = page.locator(".model-output");
  await expect(output).toContainText("First streamed fragment");
  await expect(output).toHaveText(
    "First streamed fragment plus the next fragment",
  );
  await page.getByText("Exact prompt, schema & model settings").click();
  await expect(
    page.getByText("Exact research prompt", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download full log" }),
  ).toHaveAttribute("href", /activity\/export/);
  await page.screenshot({
    path: "../outputs/research-live-ui.png",
    fullPage: true,
  });
  await page.reload();
  await page.getByRole("button", { name: /Research/ }).click();
  await expect(page.locator(".model-output")).toHaveText(
    "First streamed fragment plus the next fragment",
  );
});
