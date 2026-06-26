const pdfInput = document.getElementById("pdfInput");
const pdfName = document.getElementById("pdfName");
const templateInput = document.getElementById("templateInput");
const templateName = document.getElementById("templateName");

const compilePdfForm = document.getElementById("compilePdfForm");
const compileBtn = document.getElementById("compileBtn");
const statusText = document.getElementById("statusText");

const resultSection = document.getElementById("resultSection");
const pendingSection = document.getElementById("pendingSection");
const finalSection = document.getElementById("finalSection");

const headerOutput = document.getElementById("headerOutput");
const part1Output = document.getElementById("part1Output");
const part2Output = document.getElementById("part2Output");
const diagnosticsOutput = document.getElementById("diagnosticsOutput");

const pendingList = document.getElementById("pendingList");
const resolveBtn = document.getElementById("resolveBtn");
const finalText = document.getElementById("finalText");

const renderBtn = document.getElementById("renderBtn");
const renderStatus = document.getElementById("renderStatus");

let currentRecord = null;

function resetUiState() {
  resultSection.classList.add("hidden");
  pendingSection.classList.add("hidden");
  finalSection.classList.add("hidden");

  pendingList.innerHTML = "";
  headerOutput.textContent = "";
  part1Output.textContent = "";
  part2Output.textContent = "";
  diagnosticsOutput.textContent = "";

  renderBtn.classList.add("hidden");
  renderStatus.textContent = "";
}

function setStatus(message) {
  statusText.textContent = message || "";
}

function safeJson(value) {
  return JSON.stringify(value ?? null, null, 2);
}

function renderResult(data) {
  headerOutput.textContent = safeJson(data.header);
  part1Output.textContent = safeJson(data.part1 || []);
  part2Output.textContent = safeJson(data.part2);
  diagnosticsOutput.textContent = safeJson(data.diagnostics || []);
  resultSection.classList.remove("hidden");
}

function buildPendingInput(fieldName, suggestedValue) {
  const value = suggestedValue || "";

  if (fieldName === "data_de_praca") {
    return `<input type="date" data-field="${fieldName}" value="${value}" />`;
  }

  return `<input type="text" data-field="${fieldName}" value="${value}" placeholder="Informe o valor" />`;
}

function renderPendingFields(data) {
  pendingList.innerHTML = "";

  if (!data.pending_fields || data.pending_fields.length === 0) {
    pendingSection.classList.add("hidden");
    finalSection.classList.remove("hidden");
    renderBtn.classList.remove("hidden");
    finalText.textContent =
      "Não há pendências. A compilação já pode seguir para a próxima etapa.";
    return;
  }

  pendingSection.classList.remove("hidden");
  finalSection.classList.add("hidden");
  renderBtn.classList.add("hidden");

  data.pending_fields.forEach((pending) => {
    const item = document.createElement("div");
    item.className = "pending-item";

    item.innerHTML = `
      <h3>${pending.field_name}</h3>
      <div class="pending-meta">
        Motivo: ${pending.reason}
        ${pending.suggested_value ? `<br>Sugestão: ${pending.suggested_value}` : ""}
      </div>
      ${buildPendingInput(pending.field_name, pending.suggested_value)}
      <label class="pending-check">
        <input type="checkbox" data-save-field="${pending.field_name}" />
        <span>Salvar também na Gestão de Pessoal</span>
      </label>
    `;

    pendingList.appendChild(item);
  });
}

function buildResolvePayload() {
  const resolutions = {};
  const inputs = pendingList.querySelectorAll("[data-field]");

  inputs.forEach((input) => {
    const fieldName = input.getAttribute("data-field");
    const saveCheckbox = pendingList.querySelector(
      `[data-save-field="${fieldName}"]`
    );

    resolutions[fieldName] = {
      value: input.value || "",
      save_to_gp: saveCheckbox ? saveCheckbox.checked : false,
    };
  });

  return {
    record: currentRecord,
    resolutions,
  };
}

function validatePendingInputs() {
  const inputs = pendingList.querySelectorAll("[data-field]");
  const errors = [];

  inputs.forEach((input) => {
    const fieldName = input.getAttribute("data-field");
    const value = (input.value || "").trim();

    if (!value) {
      errors.push(`Preencha o campo pendente: ${fieldName}`);
      return;
    }

    if (fieldName === "data_de_praca") {
      const isoDatePattern = /^\d{4}-\d{2}-\d{2}$/;
      if (!isoDatePattern.test(value)) {
        errors.push("Data de praça deve estar no formato AAAA-MM-DD.");
      }
    }
  });

  return errors;
}

async function parseResponse(response, fallbackMessage) {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.detail || fallbackMessage);
  }

  return data;
}

pdfInput.parentElement.addEventListener("click", () => pdfInput.click());
templateInput.parentElement.addEventListener("click", () => templateInput.click());

pdfInput.addEventListener("change", () => {
  pdfName.textContent = pdfInput.files[0]?.name || "Nenhum arquivo selecionado";
});

templateInput.addEventListener("change", () => {
  templateName.textContent =
    templateInput.files[0]?.name || "Nenhum arquivo selecionado";
});

compilePdfForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const pdf = pdfInput.files[0];
  if (!pdf) {
    setStatus("Selecione um PDF.");
    return;
  }

  resetUiState();
  compileBtn.disabled = true;
  setStatus("Processando PDF...");

  const formData = new FormData();
  formData.append("pdf", pdf);

  try {
    const response = await fetch("/compilador/compile-pdf", {
      method: "POST",
      body: formData,
    });

    const data = await parseResponse(response, "Falha ao compilar PDF.");
    currentRecord = data;

    renderResult(data);
    renderPendingFields(data);

    setStatus(
      data.can_finalize
        ? "Compilação pronta."
        : "Pendências detectadas. Resolva para prosseguir."
    );
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Erro ao compilar o PDF.");
  } finally {
    compileBtn.disabled = false;
  }
});

resolveBtn.addEventListener("click", async () => {
  if (!currentRecord) {
    setStatus("Nenhum resultado disponível para resolver.");
    return;
  }

  const validationErrors = validatePendingInputs();
  if (validationErrors.length > 0) {
    setStatus(validationErrors[0]);
    return;
  }

  const payload = buildResolvePayload();
  setStatus("Aplicando pendências...");

  try {
    const response = await fetch("/compilador/resolve-pending", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await parseResponse(response, "Falha ao aplicar pendências.");

    currentRecord = {
      ...currentRecord,
      ...data,
    };

    renderResult(currentRecord);
    renderPendingFields(currentRecord);

    if (currentRecord.can_finalize) {
      setStatus("Pendências resolvidas. Fluxo liberado.");
      finalSection.classList.remove("hidden");
      renderBtn.classList.remove("hidden");
      finalText.textContent =
        "As pendências foram resolvidas. O próximo passo pode ser a geração do documento final.";
    } else {
      setStatus("Ainda existem pendências a resolver.");
      renderBtn.classList.add("hidden");
    }
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Erro ao resolver pendências.");
  }
});

renderBtn.addEventListener("click", async () => {
  const template = templateInput.files[0];

  if (!currentRecord) {
    renderStatus.textContent = "Nenhum registro compilado disponível.";
    return;
  }

  if (!currentRecord.can_finalize) {
    renderStatus.textContent = "Ainda existem pendências a resolver.";
    return;
  }

  if (!template) {
    renderStatus.textContent = "Selecione o modelo ODT.";
    return;
  }

  renderBtn.disabled = true;
  renderStatus.textContent = "Gerando ODT...";

  try {
    const formData = new FormData();
    formData.append("template", template);
    formData.append("record_json", JSON.stringify(currentRecord));

    const response = await fetch("/compilador/render-odt-from-record", {
      method: "POST",
      body: formData,
    });

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(data?.detail || "Falha ao gerar ODT.");
    }

    if (!data.success) {
      renderStatus.textContent =
        data.message || "Não foi possível gerar o ODT.";
      return;
    }

    renderStatus.innerHTML = `ODT gerado com sucesso.<br><code>${data.output_file}</code>`;
  } catch (error) {
    console.error(error);
    renderStatus.textContent = error.message || "Erro ao gerar ODT.";
  } finally {
    renderBtn.disabled = false;
  }
});