const form=document.querySelector('#commonSettingsForm'), keys=['provider','model','ollama_url','openai_base_url','temperature','ollama_think'];
function setModels(models,current){const select=document.querySelector('#model');select.replaceChildren(...[...new Set([current,...models].filter(Boolean))].map(x=>new Option(x,x)));if(current)select.value=current}
async function load(){const r=await fetch('/api/module-settings?module=common');if(r.status===401){location.href='/login';return}const d=await r.json(),s=d.settings||{};keys.filter(k=>k!=='model').forEach(k=>document.querySelector('#'+k).value=s[k]??'');const health=await fetch('/api/health').then(x=>x.json());setModels([],s.model||health.model);if(!s.provider)document.querySelector('#provider').value=health.provider;}
document.querySelector('#reloadModels').addEventListener('click',async()=>{const current=document.querySelector('#model').value,provider=document.querySelector('#provider').value,qs=new URLSearchParams({module:'common'});if(provider)qs.set('provider',provider);const d=await fetch('/api/models?'+qs).then(r=>r.json());setModels(d.models||[],current||d.default);document.querySelector('#result').textContent=d.error?`Không tải được model: ${d.error}`:`Đã tải ${(d.models||[]).length} model.`});
form.addEventListener('submit',async e=>{e.preventDefault();const body={};keys.forEach(k=>body[k]=document.querySelector('#'+k).value);const r=await fetch('/api/module-settings?module=common',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();document.querySelector('#result').textContent=r.ok?'Đã lưu cài đặt chung.':(d.error||'Không lưu được')});load();

const featureFlagsForm=document.querySelector('#featureFlagsForm'), flagKeys=['home','work','crm','image_generation'];
async function loadFeatureFlags(){const me=await fetch('/api/auth/me').then(r=>r.json());if(me.user_type!=='admin_user')return;featureFlagsForm.classList.remove('hidden');const d=await fetch('/api/feature-flags').then(r=>r.json()),flags=d.flags||{};flagKeys.forEach(k=>document.querySelector('#flag_'+k).checked=flags[k]!==false)}
featureFlagsForm.addEventListener('submit',async e=>{e.preventDefault();const body={};flagKeys.forEach(k=>body[k]=document.querySelector('#flag_'+k).checked);const r=await fetch('/api/admin/feature-flags',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();document.querySelector('#featureFlagsResult').textContent=r.ok?'Đã lưu tính năng.':(d.error||'Không lưu được')});
loadFeatureFlags();

// --- Personas (admin only) ---

const personaEls = {
  section: document.querySelector('#personaSection'),
  activeForm: document.querySelector('#activePersonaForm'),
  activeWeb: document.querySelector('#activeWebPersona'),
  activeVoice: document.querySelector('#activeVoicePersona'),
  select: document.querySelector('#personaSelect'),
  newBtn: document.querySelector('#newPersonaBtn'),
  deleteBtn: document.querySelector('#deletePersonaBtn'),
  form: document.querySelector('#personaForm'),
  name: document.querySelector('#personaNameInput'),
  description: document.querySelector('#personaDescriptionInput'),
  webPrompt: document.querySelector('#webPersonaInput'),
  voicePrompt: document.querySelector('#voicePersonaInput'),
  memoryForm: document.querySelector('#personaMemoryForm'),
  memoryInput: document.querySelector('#personaMemoryInput'),
  memoryFile: document.querySelector('#personaMemoryFile'),
  memoryList: document.querySelector('#personaMemoryList'),
  error: document.querySelector('#personaError'),
  status: document.querySelector('#personaStatus'),
};

let personas = [];
let selectedPersonaId = null;

function selectedPersona() {
  return personas.find((item) => item.id === selectedPersonaId) || personas[0] || null;
}

function fillPersonaSelect(select, list) {
  select.replaceChildren(
    ...list.map((item) => {
      const option = document.createElement('option');
      option.value = String(item.id);
      option.textContent = item.name;
      return option;
    })
  );
}

function renderPersonaEditor() {
  fillPersonaSelect(personaEls.select, personas);
  fillPersonaSelect(personaEls.activeWeb, personas);
  fillPersonaSelect(personaEls.activeVoice, personas);
  if (selectedPersonaId) personaEls.select.value = String(selectedPersonaId);
  const item = selectedPersona();
  if (!item) {
    personaEls.name.value = '';
    personaEls.description.value = '';
    personaEls.webPrompt.value = '';
    personaEls.voicePrompt.value = '';
    personaEls.deleteBtn.disabled = true;
    personaEls.memoryList.innerHTML = '<p class="muted-note">No persona selected.</p>';
    return;
  }
  selectedPersonaId = item.id;
  personaEls.select.value = String(item.id);
  personaEls.name.value = item.name || '';
  personaEls.description.value = item.description || '';
  personaEls.webPrompt.value = item.web_system_prompt || '';
  personaEls.voicePrompt.value = item.voice_system_prompt || '';
  personaEls.deleteBtn.disabled = personas.length <= 1;
}

async function loadPersonaMemories(personaId) {
  try {
    const response = await fetch(`/api/admin/personas/${personaId}/memories`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to load memories');
    renderPersonaMemories(data.memories || []);
  } catch (error) {
    personaEls.memoryList.textContent = error.message;
  }
}

function renderPersonaMemories(memories) {
  if (memories.length === 0) {
    personaEls.memoryList.innerHTML = '<p class="muted-note">No memories yet.</p>';
    return;
  }
  personaEls.memoryList.replaceChildren(
    ...memories.map((memory) => {
      const row = document.createElement('div');
      row.className = 'memory-item';
      const text = document.createElement('span');
      const label = memory.filename ? `${memory.source_type}: ${memory.filename}` : memory.source_type;
      text.textContent = `${label} - ${memory.content}`;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'secondary';
      remove.textContent = 'Delete';
      remove.addEventListener('click', async () => {
        await fetch(`/api/admin/persona-memories/${memory.id}`, { method: 'DELETE' });
        loadPersonaMemories(selectedPersonaId);
      });
      row.append(text, remove);
      return row;
    })
  );
}

async function loadPersonas() {
  try {
    const response = await fetch('/api/admin/personas');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to load persona');
    personas = data.personas || [];
    selectedPersonaId = selectedPersonaId || data.active_web_persona_id || data.active_voice_persona_id || personas[0]?.id || null;
    renderPersonaEditor();
    if (data.active_web_persona_id) personaEls.activeWeb.value = String(data.active_web_persona_id);
    if (data.active_voice_persona_id) personaEls.activeVoice.value = String(data.active_voice_persona_id);
    if (selectedPersonaId) loadPersonaMemories(selectedPersonaId);
  } catch (error) {
    personaEls.error.textContent = error.message;
  }
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',', 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

personaEls.activeForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  personaEls.error.textContent = '';
  personaEls.status.textContent = '';
  try {
    const response = await fetch('/api/admin/personas/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        web_persona_id: Number(personaEls.activeWeb.value),
        voice_persona_id: Number(personaEls.activeVoice.value),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to apply active personas');
    personaEls.status.textContent = 'Active personas applied.';
    loadPersonas();
  } catch (error) {
    personaEls.error.textContent = error.message;
  }
});

personaEls.select.addEventListener('change', () => {
  selectedPersonaId = Number(personaEls.select.value);
  renderPersonaEditor();
  loadPersonaMemories(selectedPersonaId);
});

personaEls.newBtn.addEventListener('click', async () => {
  personaEls.error.textContent = '';
  personaEls.status.textContent = '';
  try {
    const response = await fetch('/api/admin/personas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Nhân vật mới' }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to create persona');
    selectedPersonaId = data.id;
    personaEls.status.textContent = 'Created.';
    loadPersonas();
  } catch (error) {
    personaEls.error.textContent = error.message;
  }
});

personaEls.deleteBtn.addEventListener('click', async () => {
  const item = selectedPersona();
  if (!item || personas.length <= 1) return;
  if (!window.confirm(`Delete persona "${item.name}"?`)) return;
  personaEls.error.textContent = '';
  personaEls.status.textContent = '';
  try {
    const response = await fetch(`/api/admin/personas/${item.id}`, { method: 'DELETE' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to delete persona');
    selectedPersonaId = null;
    personaEls.status.textContent = 'Deleted.';
    loadPersonas();
  } catch (error) {
    personaEls.error.textContent = error.message;
  }
});

personaEls.form.addEventListener('submit', async (event) => {
  event.preventDefault();
  personaEls.error.textContent = '';
  personaEls.status.textContent = '';
  const item = selectedPersona();
  if (!item) return;
  const name = personaEls.name.value.trim();
  const webSystemPrompt = personaEls.webPrompt.value.trim();
  const voiceSystemPrompt = personaEls.voicePrompt.value.trim();
  if (!name) {
    personaEls.error.textContent = 'name must not be empty';
    return;
  }
  if (!webSystemPrompt) {
    personaEls.error.textContent = 'web_system_prompt must not be empty';
    return;
  }
  if (!voiceSystemPrompt) {
    personaEls.error.textContent = 'voice_system_prompt must not be empty';
    return;
  }
  try {
    const response = await fetch(`/api/admin/personas/${item.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        description: personaEls.description.value.trim(),
        web_system_prompt: webSystemPrompt,
        voice_system_prompt: voiceSystemPrompt,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to save persona');
    personaEls.status.textContent = 'Saved.';
    loadPersonas();
  } catch (error) {
    personaEls.error.textContent = error.message;
  }
});

personaEls.memoryForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  personaEls.error.textContent = '';
  personaEls.status.textContent = '';
  const item = selectedPersona();
  if (!item) return;
  const file = personaEls.memoryFile.files[0];
  const note = personaEls.memoryInput.value.trim();
  if (!file && !note) {
    personaEls.error.textContent = 'memory note or file is required';
    return;
  }
  const payload = { content: note, source_type: file ? 'file' : 'note' };
  if (file) {
    payload.filename = file.name;
    payload.content_base64 = await readFileAsBase64(file);
  }
  try {
    const response = await fetch(`/api/admin/personas/${item.id}/memories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to add memory');
    personaEls.memoryInput.value = '';
    personaEls.memoryFile.value = '';
    personaEls.status.textContent = 'Memory added.';
    loadPersonas();
    loadPersonaMemories(item.id);
  } catch (error) {
    personaEls.error.textContent = error.message;
  }
});

async function loadPersonaSection() {
  const me = await fetch('/api/auth/me').then((r) => r.json());
  if (me.user_type !== 'admin_user') return;
  personaEls.section.classList.remove('hidden');
  loadPersonas();
}
loadPersonaSection();
