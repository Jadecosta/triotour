const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function setupSidebar() {
  const toggle = $('.menu-toggle');
  const sidebar = $('#sidebar');
  const overlay = $('.sidebar-overlay');
  if (!toggle || !sidebar || !overlay) return;

  const setOpen = (open) => {
    document.body.classList.toggle('sidebar-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Fechar menu principal' : 'Abrir menu principal');
    overlay.hidden = !open;
  };

  toggle.addEventListener('click', () => {
    setOpen(!document.body.classList.contains('sidebar-open'));
  });

  overlay.addEventListener('click', () => setOpen(false));
  $$('[data-sidebar-close], .sidebar .nav-item').forEach((item) => {
    item.addEventListener('click', () => setOpen(false));
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setOpen(false);
  });
}

const airlineCompanies = [
  'Azul Linhas Aéreas', 'LATAM Airlines', 'GOL Linhas Aéreas', 'TAP Air Portugal',
  'Avianca', 'Copa Airlines', 'American Airlines', 'Air France', 'KLM',
  'Iberia', 'Emirates', 'Outra'
];
const busCompanies = [
  'Guanabara', 'Gontijo', 'Itapemirim', 'Real Expresso', 'Progresso',
  'Transbrasiliana', 'Satélite Norte', 'Catedral', 'Expresso União',
  'Águia Branca', 'Outra'
];
const bedTypes = ['Solteiro', 'Casal', 'Queen', 'King', 'Beliche', 'Sofá-cama', 'Berço', 'Outro'];
const busClasses = ['Convencional', 'Executivo', 'Semi-leito', 'Leito', 'Leito-cama', 'Double decker'];
const flightClasses = ['Econômica', 'Premium economy', 'Executiva', 'Primeira classe'];

function readInitialJson(id, fallback = []) {
  const node = document.getElementById(id);
  if (!node) return fallback;
  try {
    const value = JSON.parse(node.textContent || '[]');
    return Array.isArray(value) ? value : fallback;
  } catch (error) {
    return fallback;
  }
}

let initialDays = readInitialJson('initialDaysData');
let transportes = readInitialJson('initialTransportesData');
let beds = readInitialJson('initialBedsData');

function el(tag, attrs = {}, text = '') {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (key === 'class') node.className = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  });
  if (text) node.textContent = text;
  return node;
}

function label(text, control) {
  const wrapper = el('label');
  wrapper.append(text);
  wrapper.append(control);
  return wrapper;
}

function option(value, selectedValue) {
  const opt = el('option', { value }, value);
  opt.selected = value === selectedValue;
  return opt;
}

function setSectionVisibility(checkboxId, sectionId) {
  const checkbox = $(`#${checkboxId}`);
  const section = $(`#${sectionId}`);
  if (!checkbox || !section) return;
  section.classList.toggle('is-open', checkbox.checked);
}

function updatePassengerTotal() {
  const total = ['adultos', 'criancas', 'bebes']
    .map((id) => Math.max(0, parseInt($(`#${id}`)?.value || '0', 10)))
    .reduce((sum, value) => sum + value, 0);
  const output = $('#total_passageiros');
  if (output) output.value = total;
}

function companyOptions(type) {
  return type === 'Rodoviária' ? busCompanies : airlineCompanies;
}

function classOptions(type) {
  return type === 'Rodoviária' ? busClasses : flightClasses;
}

function transportLabels(type) {
  if (type === 'Rodoviária') {
    return {
      origem: 'Rodoviária/cidade de origem*',
      destino: 'Rodoviária/cidade de destino*',
      chegada: 'Horário previsto de chegada',
      companhia: 'Empresa rodoviária',
      identificacao: 'Número/identificação da viagem',
      classe: 'Tipo de ônibus'
    };
  }
  return {
    origem: 'Origem/aeroporto de origem*',
    destino: 'Destino/aeroporto de destino*',
    chegada: 'Horário de chegada',
    companhia: 'Companhia aérea',
    identificacao: 'Número do voo',
    classe: 'Classe'
  };
}

function collectTransportes() {
  const wrap = $('#transportesWrap');
  if (!wrap) return;
  transportes = $$('.transport-card', wrap).map((card) => ({
    id: card.dataset.id || '',
    tipo_trecho: $('[data-field="tipo_trecho"]', card).value,
    tipo_passagem: $('[data-field="tipo_passagem"]', card).value,
    origem: $('[data-field="origem"]', card).value,
    destino: $('[data-field="destino"]', card).value,
    data: $('[data-field="data"]', card).value,
    horario_saida: $('[data-field="horario_saida"]', card).value,
    horario_chegada: $('[data-field="horario_chegada"]', card).value,
    companhia: $('[data-field="companhia"]', card).value,
    companhia_personalizada: $('[data-field="companhia_personalizada"]', card).value,
    identificacao: $('[data-field="identificacao"]', card).value,
    classe: $('[data-field="classe"]', card).value,
    bagagem: $('[data-field="bagagem"]', card).value,
    observacoes: $('[data-field="observacoes"]', card).value
  }));
  const hidden = $('#transportes_json');
  if (hidden) hidden.value = JSON.stringify(transportes);
}

function renderTransportes() {
  const wrap = $('#transportesWrap');
  if (!wrap) return;
  wrap.replaceChildren();
  transportes.forEach((tr, index) => {
    const card = el('div', { class: 'transport-card', dataset: { id: tr.id || '' } });
    const type = tr.tipo_passagem || 'Aérea';
    const labels = transportLabels(type);

    const header = el('div', { class: 'transport-header' });
    header.append(el('strong', {}, `Trecho ${index + 1}`));
    const actions = el('div', { class: 'inline-actions' });
    const up = el('button', { type: 'button', disabled: index === 0 }, '↑');
    const down = el('button', { type: 'button', disabled: index === transportes.length - 1 }, '↓');
    const remove = el('button', { type: 'button', class: 'danger-btn' }, 'Remover');
    up.addEventListener('click', () => { collectTransportes(); [transportes[index - 1], transportes[index]] = [transportes[index], transportes[index - 1]]; renderTransportes(); });
    down.addEventListener('click', () => { collectTransportes(); [transportes[index + 1], transportes[index]] = [transportes[index], transportes[index + 1]]; renderTransportes(); });
    remove.addEventListener('click', () => {
      const ok = tr.id ? confirm('Remover este trecho salvo?') : true;
      if (!ok) return;
      collectTransportes();
      transportes.splice(index, 1);
      renderTransportes();
    });
    actions.append(up, down, remove);
    header.append(actions);

    const row1 = el('div', { class: 'cols' });
    const tipoTrecho = el('select', { dataset: { field: 'tipo_trecho' } });
    ['Ida', 'Volta', 'Conexão', 'Trecho adicional'].forEach((value) => tipoTrecho.append(option(value, tr.tipo_trecho || 'Ida')));
    const tipoPassagem = el('select', { dataset: { field: 'tipo_passagem' } });
    ['Aérea', 'Rodoviária'].forEach((value) => tipoPassagem.append(option(value, type)));
    tipoPassagem.addEventListener('change', () => { collectTransportes(); renderTransportes(); });
    row1.append(label('Tipo do trecho*', tipoTrecho), label('Tipo de passagem*', tipoPassagem));

    const origem = el('input', { value: tr.origem || '', dataset: { field: 'origem' } });
    const destino = el('input', { value: tr.destino || '', dataset: { field: 'destino' } });
    const data = el('input', { type: 'date', value: tr.data || '', dataset: { field: 'data' } });
    const row2 = el('div', { class: 'cols' });
    row2.append(label(labels.origem, origem), label(labels.destino, destino), label('Data*', data));

    const saida = el('input', { type: 'time', value: tr.horario_saida || '', dataset: { field: 'horario_saida' } });
    const chegada = el('input', { type: 'time', value: tr.horario_chegada || '', dataset: { field: 'horario_chegada' } });
    const companhia = el('select', { dataset: { field: 'companhia' } });
    companyOptions(type).forEach((value) => companhia.append(option(value, tr.companhia || '')));
    const row3 = el('div', { class: 'cols' });
    row3.append(label('Horário de saída', saida), label(labels.chegada, chegada), label(labels.companhia, companhia));

    const outra = label('Outra companhia/empresa', el('input', { value: tr.companhia_personalizada || '', dataset: { field: 'companhia_personalizada' } }));
    outra.className = 'other-company';
    outra.hidden = companhia.value !== 'Outra';
    companhia.addEventListener('change', () => { outra.hidden = companhia.value !== 'Outra'; });

    const identificacao = el('input', { value: tr.identificacao || '', dataset: { field: 'identificacao' } });
    const classe = el('select', { dataset: { field: 'classe' } });
    classe.append(option('', tr.classe || ''));
    classOptions(type).forEach((value) => classe.append(option(value, tr.classe || '')));
    const bagagem = el('input', { value: tr.bagagem || '', dataset: { field: 'bagagem' } });
    const row4 = el('div', { class: 'cols' });
    row4.append(label(labels.identificacao, identificacao), label(labels.classe, classe), label('Bagagem', bagagem));

    const obs = el('textarea', { placeholder: 'Observações', value: tr.observacoes || '', dataset: { field: 'observacoes' } });
    card.append(header, row1, row2, row3, outra, row4, obs);
    wrap.append(card);
  });
  collectTransportes();
}

function addTransport() {
  collectTransportes();
  transportes.push({ tipo_trecho: transportes.length ? 'Trecho adicional' : 'Ida', tipo_passagem: 'Aérea' });
  renderTransportes();
}

function collectBeds() {
  const wrap = $('#bedsWrap');
  if (!wrap) return;
  beds = $$('.bed-row', wrap).map((row) => ({
    tipo: $('[data-field="tipo"]', row).value,
    quantidade: $('[data-field="quantidade"]', row).value
  })).filter((bed) => bed.tipo || bed.quantidade);
  const hidden = $('#camas_json');
  if (hidden) hidden.value = JSON.stringify(beds);
}

function renderBeds() {
  const wrap = $('#bedsWrap');
  if (!wrap) return;
  wrap.replaceChildren();
  beds.forEach((bed, index) => {
    const row = el('div', { class: 'cols bed-row' });
    const tipo = el('select', { dataset: { field: 'tipo' } });
    tipo.append(option('', bed.tipo || ''));
    bedTypes.forEach((value) => tipo.append(option(value, bed.tipo || '')));
    const qtd = el('input', { type: 'number', min: '0', value: bed.quantidade || 1, dataset: { field: 'quantidade' } });
    const remove = el('button', { type: 'button', class: 'danger-btn' }, 'Remover');
    remove.addEventListener('click', () => { collectBeds(); beds.splice(index, 1); renderBeds(); });
    row.append(label('Tipo de cama', tipo), label('Quantidade', qtd), remove);
    wrap.append(row);
  });
  collectBeds();
}

function collectHotelItems() {
  const hidden = $('#hospedagem_itens_json');
  if (!hidden) return;
  hidden.value = JSON.stringify($$('#hotelItems input:checked').map((input) => input.value));
}

function updateHotelOtherFields() {
  const accommodation = $('#tipo_acomodacao');
  const accommodationOther = $('.other-accommodation');
  if (accommodation && accommodationOther) accommodationOther.hidden = accommodation.value !== 'Outro';
  const hotelOther = $('.hotel-items-other');
  const hasOther = $$('#hotelItems input:checked').some((input) => input.value === 'Outros');
  if (hotelOther) hotelOther.hidden = !hasOther;
}

function updateDiarias() {
  const checkin = $('#checkin')?.value;
  const checkout = $('#checkout')?.value;
  const output = $('#diarias');
  if (!output || !checkin || !checkout) {
    if (output) output.value = 0;
    return;
  }
  const start = new Date(`${checkin}T00:00:00`);
  const end = new Date(`${checkout}T00:00:00`);
  const days = Math.round((end - start) / 86400000);
  output.value = Number.isFinite(days) ? Math.max(0, days) : 0;
}

function updateHotelInstallment() {
  const total = parseFloat($('#hosp_valor_total')?.value || '0');
  const parcelas = parseInt($('#hosp_parcelas')?.value || '1', 10);
  const output = $('#hosp_valor_parcelado');
  if (output && total >= 0 && parcelas > 0 && !output.dataset.touched) {
    output.value = (total / parcelas).toFixed(2);
  }
}

function setupPromotionForm() {
  const total = $('#preco_promocional');
  const parcelas = $('#promo_parcelas');
  const parcela = $('#valor_parcela');
  const update = () => {
    if (!total || !parcelas || !parcela || parcela.dataset.touched) return;
    const amount = parseFloat(total.value || '0');
    const count = parseInt(parcelas.value || '1', 10);
    if (amount >= 0 && count > 0) parcela.value = (amount / count).toFixed(2);
  };
  total?.addEventListener('input', update);
  parcelas?.addEventListener('input', update);
  parcela?.addEventListener('input', (event) => { event.target.dataset.touched = '1'; });

  $$('input[type="file"][data-preview]').forEach((input) => {
    input.addEventListener('change', () => {
      const preview = document.getElementById(input.dataset.preview);
      if (!preview) return;
      preview.replaceChildren();
      [...input.files].forEach((file) => {
        if (!file.type.startsWith('image/')) return;
        const img = el('img', { alt: file.name });
        img.src = URL.createObjectURL(file);
        img.addEventListener('load', () => URL.revokeObjectURL(img.src), { once: true });
        preview.append(img);
      });
    });
  });
}

const wrap = document.getElementById('days');
function renderDays() {
  if (!wrap) return;
  wrap.replaceChildren();
  initialDays.forEach((d, i) => {
    const box = el('div', { class: 'day-editor' });
    box.append(el('b', {}, `Dia ${i + 1}`));
    const row = el('div', { class: 'cols' });
    row.append(
      el('input', { placeholder: 'Dia do roteiro', value: d.dia || `Dia ${i + 1}` }),
      el('input', { type: 'date', value: d.data || '' }),
      el('input', { placeholder: 'Cidade/local', value: d.local || '' }),
      el('input', { placeholder: 'Horário', value: d.horario || '' })
    );
    box.append(row);
    box.append(el('input', { placeholder: 'Título da programação', value: d.titulo || '' }));
    box.append(el('textarea', { placeholder: 'Descrição detalhada', value: d.descricao || '' }));
    box.append(el('textarea', { placeholder: 'Observações', value: d.observacoes || '' }));
    const actions = el('div', { class: 'inline-actions' });
    const up = el('button', { type: 'button' }, '↑');
    const down = el('button', { type: 'button' }, '↓');
    const remove = el('button', { type: 'button', class: 'danger-btn' }, 'Remover');
    up.addEventListener('click', () => moveDay(i, -1));
    down.addEventListener('click', () => moveDay(i, 1));
    remove.addEventListener('click', () => removeDay(i));
    actions.append(up, down, remove);
    box.append(actions);
    wrap.append(box);
  });
}

function collectDays() {
  if (!wrap) return;
  initialDays = [...wrap.children].map((node) => {
    const inputs = node.querySelectorAll('input');
    const text = node.querySelectorAll('textarea');
    return {
      dia: inputs[0].value, data: inputs[1].value, local: inputs[2].value,
      horario: inputs[3].value, titulo: inputs[4].value,
      descricao: text[0].value, observacoes: text[1].value
    };
  });
  const hidden = document.getElementById('roteiro_json');
  if (hidden) hidden.value = JSON.stringify(initialDays);
}

function addDay() {
  collectDays();
  initialDays.push({ dia: `Dia ${initialDays.length + 1}` });
  renderDays();
}

function removeDay(index) {
  collectDays();
  initialDays.splice(index, 1);
  renderDays();
}

function moveDay(index, direction) {
  collectDays();
  const target = index + direction;
  if (target < 0 || target >= initialDays.length) return;
  [initialDays[index], initialDays[target]] = [initialDays[target], initialDays[index]];
  renderDays();
}

document.addEventListener('DOMContentLoaded', () => {
  setupSidebar();
  ['adultos', 'criancas', 'bebes'].forEach((id) => $(`#${id}`)?.addEventListener('input', updatePassengerTotal));
  $('#inclui_passagens')?.addEventListener('change', () => {
    setSectionVisibility('inclui_passagens', 'passagens_section');
    if ($('#inclui_passagens').checked && !transportes.length) addTransport();
    collectTransportes();
  });
  $('#inclui_hospedagem')?.addEventListener('change', () => setSectionVisibility('inclui_hospedagem', 'hospedagem_section'));
  $('#addTransport')?.addEventListener('click', addTransport);
  $('#addBed')?.addEventListener('click', () => { collectBeds(); beds.push({ tipo: '', quantidade: 1 }); renderBeds(); });
  $('#tipo_acomodacao')?.addEventListener('change', updateHotelOtherFields);
  $$('#hotelItems input').forEach((input) => input.addEventListener('change', () => { updateHotelOtherFields(); collectHotelItems(); }));
  $('#checkin')?.addEventListener('change', updateDiarias);
  $('#checkout')?.addEventListener('change', updateDiarias);
  $('#hosp_valor_total')?.addEventListener('input', updateHotelInstallment);
  $('#hosp_parcelas')?.addEventListener('input', updateHotelInstallment);
  $('#hosp_valor_parcelado')?.addEventListener('input', (event) => { event.target.dataset.touched = '1'; });
  $('#proposalForm')?.addEventListener('submit', () => {
    collectTransportes();
    collectBeds();
    collectHotelItems();
    collectDays();
  });

  setSectionVisibility('inclui_passagens', 'passagens_section');
  setSectionVisibility('inclui_hospedagem', 'hospedagem_section');
  updatePassengerTotal();
  updateHotelOtherFields();
  updateDiarias();
  renderTransportes();
  renderBeds();
  collectHotelItems();
  renderDays();
  setupPromotionForm();
});
