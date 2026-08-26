// The panel, drawn by hand. No build step: the window loads these three files
// straight from disk, so a change is visible on reload and nothing compiles.

let STATE = { keys: [], feeds: [], token_pending: false, bot_running: false };
let TAB = "keys";
let OFFLINE = false;

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

// A dropdown that lays its options out in two columns. Native selects cannot
// do that, and a one-column list of models or subreddits is mostly scrollbar.
let openMenu = null;

function dropdown(options, value, onPick, note) {
  const wrap = el("div", "dd");
  const button = el("button", "act");
  const label = el("span", "picked");
  const caret = el("span", "caret", "▼");
  const chosen = options.find((option) => option[0] === value);
  label.textContent = chosen ? chosen[1] : (options[0] ? options[0][1] : "—");
  button.append(label, caret);
  wrap.append(button);

  const close = () => {
    if (openMenu && openMenu.parentNode) openMenu.remove();
    openMenu = null;
  };

  button.onclick = (event) => {
    event.stopPropagation();
    const already = openMenu && openMenu.dataset.owner === String(wrap.dataset.id);
    close();
    if (already) return;
    // Two columns always — a single option is the only case where a second
    // column would be an empty half.
    const menu = el("div", "dd-menu" + (options.length < 2 ? " one" : ""));
    wrap.dataset.id = wrap.dataset.id || String(Math.random());
    menu.dataset.owner = wrap.dataset.id;
    if (note) menu.append(el("div", "note-row", note));
    options.forEach(([id, text]) => {
      const item = el("button", id === value ? "on" : null, text);
      item.onclick = (e) => {
        e.stopPropagation();
        close();
        label.textContent = text;
        onPick(id);
      };
      menu.append(item);
    });
    wrap.append(menu);
    openMenu = menu;
  };

  return wrap;
}

document.addEventListener("click", () => {
  if (openMenu && openMenu.parentNode) openMenu.remove();
  openMenu = null;
});

let toastTimer = null;
function toast(text, kind) {
  const node = $("#toast");
  node.textContent = text;
  node.className = "show " + (kind || "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (node.className = ""), 2600);
}

// --------------------------------------------------------------------- shell

function drawHeader() {
  const pick = $("#feedpick");
  pick.textContent = "";
  if (STATE.feeds.length) {
    const active = STATE.feeds.find((feed) => feed.active);
    pick.append(el("span", "hint", "Лента:"), dropdown(
      STATE.feeds.map((feed) => [feed.id, feed.name + " · " + feed.sources]),
      active ? active.id : null,
      async (id) => {
        STATE.feeds = (await api("/api/feeds/activate", { id })).feeds;
        SOURCES = ITEMS = LOOK = null;  // they belong to the feed we just left
        draw();
        toast("лента переключена");
      },
    ));
  } else {
    pick.append(el("span", "hint", "лент пока нет"));
  }

  const state = $("#state");
  state.textContent = "";
  if (OFFLINE) {
    // The panel lives inside the bot process, so losing it means the bot is
    // gone — worth saying out loud instead of quietly showing stale numbers.
    state.append(el("i", null, "приложение не отвечает"));
  } else if (STATE.token_pending) {
    state.append(el("i", null, "токен принят — бот поднимается сам"));
  } else if (STATE.bot_running) {
    state.append(el("b", null, "бот на связи"));
  } else {
    state.append(el("i", null, "нет токена Telegram"));
  }
}

function drawNav() {
  const nav = $("#nav");
  nav.textContent = "";
  [["keys", "Ключи"], ["models", "Модели"], ["feeds", "Ленты"],
   ["sources", "Источники"], ["posts", "Посты"], ["look", "Вид"]]
    .forEach(([id, label]) => {
    const button = el("button", TAB === id ? "on" : null, label);
    button.onclick = () => { TAB = id; draw(); };
    nav.append(button);
  });
}

// ---------------------------------------------------------------------- keys

function keyCard(key) {
  const card = el("div", "card");

  const head = el("div", "row");
  head.append(el("span", "dot " + (key.filled ? "on" : key.required ? "need" : "")));
  head.append(el("span", "label", key.label));
  head.append(el("span", "hint", key.hint));
  const mask = el("span", "mask grow", key.mask || "");
  mask.style.textAlign = "right";
  head.append(mask);
  card.append(head);

  const line = el("div", "row");
  const input = el("input", "grow");
  input.type = "password";
  input.placeholder = key.filled ? "новое значение" : key.env;
  input.spellcheck = false;
  line.append(input);

  const save = el("button", "act primary", "Сохранить");
  input.onkeydown = (e) => { if (e.key === "Enter") save.click(); };
  save.onclick = async () => {
    const value = input.value.trim();
    if (!value) return toast("пусто", "bad");
    save.disabled = true;
    save.textContent = "проверяю…";
    try {
      // Checked against the service before it is stored, so a typo never
      // becomes a key the app quietly starts up with.
      const res = await api("/api/keys/set", { id: key.id, value });
      if (res.ok) {
        input.value = "";
        toast(key.label + ": " + res.note, "good");
        await reload();
      } else {
        toast(key.label + ": " + res.note, "bad");
      }
    } catch (err) {
      toast(String(err.message || err), "bad");
    } finally {
      save.disabled = false;
      save.textContent = "Сохранить";
    }
  };
  line.append(save);

  if (key.filled) {
    const show = el("button", "act", "Показать");
    show.onclick = async () => {
      if (input.type === "text") {
        input.type = "password";
        input.value = "";
        show.textContent = "Показать";
        return;
      }
      input.value = (await api("/api/keys/reveal", { id: key.id })).value;
      input.type = "text";
      show.textContent = "Скрыть";
    };
    line.append(show);

    const check = el("button", "act", "Проверить");
    check.onclick = async () => {
      check.disabled = true;
      const res = await api("/api/keys/check", { id: key.id, value: input.value.trim() });
      check.disabled = false;
      toast(key.label + ": " + res.note, res.ok ? "good" : "bad");
    };
    line.append(check);

    const drop = el("button", "act danger", "Стереть");
    drop.onclick = async () => {
      if (drop.dataset.armed !== "1") {
        drop.dataset.armed = "1";
        drop.textContent = "Точно стереть?";
        return;
      }
      await api("/api/keys/clear", { id: key.id });
      toast(key.label + " стёрт");
      await reload();
    };
    line.append(drop);
  }

  card.append(line);
  return card;
}

function drawKeys(main) {
  main.append(el("h2", null, "Ключи"));
  main.append(el("p", "note",
    "Значение не приходит вместе со страницей — только по кнопке «Показать». " +
    "Каждый ключ проверяется живым запросом до того, как его сохранят."));
  STATE.keys.forEach((key) => main.append(keyCard(key)));
}

// --------------------------------------------------------------------- feeds

function feedCard(feed) {
  const card = el("div", "card");

  const head = el("div", "row");
  head.append(el("span", "dot " + (feed.active ? "on" : "")));
  const name = el("input", "grow");
  name.value = feed.name;
  head.append(name);
  const note = el("input", "grow");
  note.value = feed.note;
  note.placeholder = "о чём эта ниша, своими словами";
  head.append(note);
  card.append(head);

  let line = el("div", "row");
  line.append(el("span", "hint", "окно"));
  const window_ = el("input");
  window_.type = "number";
  window_.value = feed.window_days;
  window_.style.width = "70px";
  window_.title = "как глубоко в прошлое смотрит сбор, в днях";
  line.append(window_, el("span", "hint", "дней · выдержка"));

  // The one number that decides whether ranking works at all: a post younger
  // than this has not been voted on, so its score says nothing.
  const hold = el("input");
  hold.type = "number";
  hold.value = feed.hold_days;
  hold.style.width = "70px";
  hold.title = "не брать посты моложе этого — они ещё не набрали голосов";
  line.append(hold, el("span", "hint grow", "дней · " + feed.sources + " источн."));
  card.append(line);

  const reel = el("div", "row");
  reel.append(el("span", "hint", "ролик"));
  const seconds = el("input");
  seconds.type = "number";
  seconds.value = feed.reel_seconds;
  seconds.style.width = "70px";
  seconds.title = "длина ролика в секундах — от неё считается число битов";
  reel.append(seconds, el("span", "hint", "сек · голос"));

  let chosenVoice = feed.voice;
  reel.append(dropdown(
    (STATE.voices || []).map((v) => [v.id, v.label]),
    feed.voice,
    (id) => { chosenVoice = id; },
  ), el("span", "hint", "темп"));

  // Edge ignores its own rate parameter on Russian voices, so tempo is applied
  // on playback and the word timings are divided by the same number.
  const tempo = el("input");
  tempo.type = "number";
  tempo.step = "0.05";
  tempo.value = feed.voice_tempo;
  tempo.style.width = "78px";
  tempo.title = "ускорение речи при воспроизведении";
  reel.append(tempo, el("span", "hint grow", ""));
  card.append(reel);

  line = el("div", "row");

  const save = el("button", "act", "Сохранить");
  save.onclick = async () => {
    try {
      STATE.feeds = (await api("/api/feeds/update", {
        id: feed.id, name: name.value, note: note.value,
        window_days: +window_.value, hold_days: +hold.value,
        reel_seconds: +seconds.value, voice: chosenVoice, voice_tempo: +tempo.value,
      })).feeds;
      draw();
      toast("сохранено");
    } catch (err) {
      toast(String(err.message || err), "bad");
    }
  };
  line.append(save);

  if (!feed.active) {
    const use = el("button", "act", "Сделать активной");
    use.onclick = async () => {
      STATE.feeds = (await api("/api/feeds/activate", { id: feed.id })).feeds;
      SOURCES = ITEMS = null;
      draw();
    };
    line.append(use);
  }

  // Destructive, so it asks on the button itself rather than in a dialog that
  // can be dismissed by muscle memory.
  const drop = el("button", "act danger", "Удалить");
  drop.onclick = async () => {
    if (drop.dataset.armed !== "1") {
      drop.dataset.armed = "1";
      drop.textContent = "Удалить «" + feed.name + "» насовсем?";
      return;
    }
    STATE.feeds = (await api("/api/feeds/delete", { id: feed.id })).feeds;
    SOURCES = null;
    draw();
    toast("лента удалена");
  };
  line.append(drop);

  card.append(line);
  return card;
}

function drawFeeds(main) {
  main.append(el("h2", null, "Ленты"));
  main.append(el("p", "note",
    "Лента — одна ниша: свой набор сабреддитов, свой канал, свой выпуск. " +
    "Активная лента — та, с которой работает бот."));

  const add = el("div", "card");
  const row = el("div", "row");
  const name = el("input", "grow");
  name.placeholder = "название ленты";
  const note = el("input", "grow");
  note.placeholder = "о чём она";
  const make = el("button", "act primary", "Завести");
  make.onclick = async () => {
    if (!name.value.trim()) return toast("нужно имя", "bad");
    try {
      STATE.feeds = (await api("/api/feeds/create",
        { name: name.value, note: note.value })).feeds;
      SOURCES = null;  // a brand new feed starts with none
      name.value = note.value = "";
      draw();
      toast("лента заведена", "good");
    } catch (err) {
      toast(String(err.message || err), "bad");
    }
  };
  row.append(name, note, make);
  add.append(row);
  main.append(add);

  if (!STATE.feeds.length) {
    main.append(el("div", "empty",
      "Ни одной ленты. Заведи первую — дальше к ней добавятся источники."));
    return;
  }
  STATE.feeds.forEach((feed) => main.append(feedCard(feed)));
}

// ------------------------------------------------------------------ sources

let SOURCES = null; // {subs, catalog} for the active feed, loaded on demand

function ago(stamp) {
  if (!stamp) return "ещё не запускался";
  const mins = Math.round((Date.now() / 1000 - stamp) / 60);
  if (mins < 60) return mins + " мин назад";
  const hours = Math.round(mins / 60);
  if (hours < 48) return hours + " ч назад";
  return Math.round(hours / 24) + " дн назад";
}

function thousands(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace(".0", "") + "M";
  if (n >= 1000) return Math.round(n / 1000) + "k";
  return String(n || 0);
}

function subCard(sub) {
  const card = el("div", "card");

  const head = el("div", "row");
  // The dot is the switch: a source is either being swept or it is not, and
  // that is worth one click, not a trip into a submenu.
  const dot = el("span", "dot " + (sub.enabled ? "on" : ""));
  dot.style.cursor = "pointer";
  dot.title = sub.enabled ? "собирается — выключить" : "выключен — включить";
  head.append(dot);

  head.append(el("span", "label", (sub.adapter === "reddit" ? "r/" : "") + sub.name));
  if (sub.subscribers) head.append(el("span", "hint", thousands(sub.subscribers)));
  head.append(el("span", "hint grow", sub.about.slice(0, 70)));
  head.append(el("span", "hint", "собрано " + sub.stored + " · в ленту " + sub.kept));
  head.append(el("span", "hint", ago(sub.last_run_at)));
  card.append(head);

  const line = el("div", "row");
  const words = el("input", "grow");
  words.value = sub.queries.join(", ");
  words.placeholder = "ключевые слова через запятую — пусто значит весь саб";
  line.append(words);

  // How much of the subreddit one sweep takes. Without it a big sub would be
  // pulled down a hundred posts at a time until the window ran out.
  const budget = el("input");
  budget.type = "number";
  budget.min = "1";
  budget.max = "1000";
  budget.value = sub.limit_posts;
  budget.title = "сколько постов забирать за прогон";
  budget.style.width = "84px";
  line.append(el("span", "hint", "постов"), budget);

  const save = el("button", "act", "Сохранить");
  const push = async (enabled) => {
    SOURCES = await api("/api/sources/update", {
      id: sub.id,
      queries: words.value.split(",").map((w) => w.trim()).filter(Boolean),
      limit_posts: +budget.value || sub.limit_posts,
      enabled,
    });
    draw();
  };
  save.onclick = () => push(sub.enabled).then(() => toast("сохранено"));
  dot.onclick = () => push(!sub.enabled);
  words.onkeydown = (e) => { if (e.key === "Enter") save.click(); };
  line.append(save);

  const drop = el("button", "act danger", "Убрать");
  drop.onclick = async () => {
    if (drop.dataset.armed !== "1") {
      drop.dataset.armed = "1";
      drop.textContent = "Убрать из ленты?";
      return;
    }
    SOURCES = await api("/api/sources/remove", { id: sub.id });
    draw();
    toast("источник убран");
  };
  line.append(drop);

  card.append(line);
  return card;
}

function addSourceCard() {
  const card = el("div", "card");
  const row = el("div", "row");

  const adapters = STATE.adapters || [];
  let chosenAdapter = adapters.length ? adapters[0].id : "reddit";
  const name = el("input", "grow");
  const spec = () => adapters.find((a) => a.id === chosenAdapter) || {};
  name.placeholder = spec().name_hint || "имя источника";
  row.append(dropdown(
    adapters.map((a) => [a.id, a.label]),
    chosenAdapter,
    (id) => { chosenAdapter = id; name.placeholder = spec().name_hint || "имя источника"; },
  ));

  const words = el("input", "grow");
  words.placeholder = "ключевые слова (необязательно)";

  const add = el("button", "act primary", "Добавить");
  add.onclick = async () => {
    if (!name.value.trim()) return toast("нужно имя", "bad");
    add.disabled = true;
    add.textContent = "проверяю…";
    try {
      // The server looks the name up before saving, so a typo never becomes a
      // source that quietly sweeps nothing for a week.
      const res = await api("/api/sources/add", {
        adapter: chosenAdapter,
        name: name.value,
        queries: words.value.split(",").map((w) => w.trim()).filter(Boolean),
      });
      if (!res.ok) {
        toast(res.note, "bad");
      } else {
        SOURCES = res;
        name.value = words.value = "";
        draw();
        toast("источник добавлен", "good");
      }
    } catch (err) {
      toast(String(err.message || err), "bad");
    } finally {
      add.disabled = false;
      add.textContent = "Добавить";
    }
  };
  name.onkeydown = (e) => { if (e.key === "Enter") add.click(); };

  row.append(name, words, add);
  card.append(row);
  return card;
}

function catalogCard(shelf) {
  const card = el("div", "card");
  card.append(el("div", "hint",
    "Уже собираются для других лент — подписка бесплатна, история уже в пуле:"));
  const row = el("div", "row");
  row.style.flexWrap = "wrap";
  shelf.forEach((source) => {
    const button = el("button", "act",
      (source.adapter === "reddit" ? "r/" : "") + source.name + "  ·  " + source.items);
    button.onclick = async () => {
      SOURCES = await api("/api/sources/subscribe", { source_id: source.id });
      draw();
      toast("подписал ленту");
    };
    row.append(button);
  });
  card.append(row);
  return card;
}

function drawSources(main) {
  const feed = (STATE.feeds || []).find((f) => f.active);
  main.append(el("h2", null, "Источники" + (feed ? " · " + feed.name : "")));
  main.append(el("p", "note",
    "Ниша — это набор сабреддитов. Слова необязательны: без них берётся весь саб, " +
    "со словами — только посты, где они встречаются. Сам саб качается один раз на все ленты."));

  if (!feed) {
    main.append(el("div", "empty", "Сначала заведи ленту на соседней вкладке."));
    return;
  }
  if (SOURCES === null) {
    main.append(el("div", "empty", "…"));
    loadSources();
    return;
  }

  main.append(addSourceCard());
  if (!SOURCES.subs.length) {
    main.append(el("div", "empty", "Ни одного источника. Добавь первый сабреддит."));
  }
  SOURCES.subs.forEach((sub) => main.append(subCard(sub)));
  if (SOURCES.catalog.length) main.append(catalogCard(SOURCES.catalog));
}

async function loadSources() {
  try {
    SOURCES = await api("/api/sources");
  } catch (err) {
    SOURCES = { subs: [], catalog: [] };
  }
  if (TAB === "sources") draw();
}

// -------------------------------------------------------------------- models

let MODELS = null;

function modelField(field) {
  const card = el("div", "card");

  const head = el("div", "row");
  head.append(el("span", "label", field.label));
  head.append(el("span", "hint grow", field.hint));
  // Whether this is still the built-in value or something you set.
  const changed = String(field.value) !== String(field.default);
  head.append(el("span", "hint", changed ? "изменено" : "по умолчанию"));
  card.append(head);

  const line = el("div", "row");
  const input = el("input", "grow");
  input.value = field.value;
  if (field.kind !== "line") {
    input.type = "number";
    input.step = field.kind === "float" ? "0.05" : "1";
  }
  line.append(input);

  const save = el("button", "act primary", "Сохранить");
  save.onclick = async () => {
    try {
      MODELS = (await api("/api/models/set",
        { key: field.key, value: input.value })).fields;
      draw();
      toast("сохранено", "good");
    } catch (err) {
      toast(String(err.message || err), "bad");
    }
  };
  input.onkeydown = (e) => { if (e.key === "Enter") save.click(); };
  line.append(save);

  if (field.kind === "line") {
    const check = el("button", "act", "Проверить");
    check.onclick = async () => {
      check.disabled = true;
      check.textContent = "спрашиваю…";
      const res = await api("/api/models/check", { model: input.value.trim() });
      check.disabled = false;
      check.textContent = "Проверить";
      toast(res.note, res.ok ? "good" : "bad");
    };
    line.append(check);
  }

  if (changed) {
    const back = el("button", "act", "Вернуть");
    back.onclick = async () => {
      MODELS = (await api("/api/models/reset", { key: field.key })).fields;
      draw();
      toast("вернул значение по умолчанию");
    };
    line.append(back);
  }

  card.append(line);
  return card;
}

function drawModels(main) {
  main.append(el("h2", null, "Модели"));
  main.append(el("p", "note",
    "Всё идёт через OpenRouter. Применяется сразу, перезапуск не нужен. " +
    "«Проверить» шлёт настоящий короткий запрос — опечатка в имени модели видна здесь, " +
    "а не посреди прогона."));
  if (MODELS === null) {
    main.append(el("div", "empty", "…"));
    loadModels();
    return;
  }
  MODELS.forEach((field) => main.append(modelField(field)));
}

async function loadModels() {
  try {
    MODELS = (await api("/api/models")).fields;
  } catch (err) {
    MODELS = [];
  }
  if (TAB === "models") draw();
}

// ----------------------------------------------------------------------- look

let LOOK = null;

function themeField(field) {
  const card = el("div", "card");
  const row = el("div", "row");
  row.append(el("span", "label", field.label));

  let input;
  if (field.kind === "color") {
    input = el("input");
    input.type = "color";
    input.value = field.value;
    input.style.cssText = "width:56px;padding:2px";
  } else if (field.kind === "bool") {
    input = el("input");
    input.type = "checkbox";
    input.checked = !!field.value;
    input.style.cssText = "width:20px;height:20px";
  } else if (field.kind === "select") {
    input = dropdown(field.options || [], field.value, async (id) => {
      try {
        LOOK.fields = (await api("/api/theme/set", {key: field.key, value: id})).fields;
        draw();
      } catch (err) {
        toast(String(err.message || err), "bad");
      }
    });
    row.append(input);
    row.append(el("span", "hint grow", field.hint));
    card.append(row);
    return card;
  } else {
    input = el("input");
    input.type = field.kind === "line" ? "text" : "number";
    if (field.kind === "float") input.step = "0.01";
    input.value = field.value;
    input.style.width = field.kind === "line" ? "180px" : "90px";
  }
  row.append(input);
  row.append(el("span", "hint grow", field.hint));

  // Settings change the picture at once — no Apply button for something this
  // cheap; the only expensive action here is the render itself.
  const push = async () => {
    const value = field.kind === "bool" ? input.checked : input.value;
    try {
      LOOK.fields = (await api("/api/theme/set", {key: field.key, value})).fields;
      const changed = LOOK.fields.find((f) => f.key === field.key);
      mark.textContent = String(changed.value) === String(changed.default)
        ? "по умолчанию" : "изменено";
    } catch (err) {
      toast(String(err.message || err), "bad");
    }
  };
  input.onchange = push;

  const mark = el("span", "hint",
    String(field.value) === String(field.default) ? "по умолчанию" : "изменено");
  row.append(mark);

  const back = el("button", "act", "Вернуть");
  back.onclick = async () => {
    LOOK.fields = (await api("/api/theme/reset", {key: field.key})).fields;
    draw();
  };
  row.append(back);

  card.append(row);
  return card;
}

function drawLook(main) {
  const feed = (STATE.feeds || []).find((f) => f.active);
  main.append(el("h2", null, "Вид" + (feed ? " · " + feed.name : "")));
  main.append(el("p", "note",
    "Настройки этой ленты. Меняются сразу и применяются на следующем рендере."));
  if (!feed) {
    main.append(el("div", "empty", "Сначала заведи ленту."));
    return;
  }
  if (LOOK === null) {
    main.append(el("div", "empty", "…"));
    loadLook();
    return;
  }

  if (!LOOK.engine.ok) {
    const warn = el("div", "card");
    warn.append(el("div", "row")).append(el("span", "label", "Движок: " + LOOK.engine.note));
    main.append(warn);
  }

  const picker = el("div", "card");
  picker.append(el("div", "hint", "Пакет — под какие посты эта лента:"));
  LOOK.packs.forEach((pack) => {
    const row = el("div", "row");
    const button = el("button", "act" + (pack.id === LOOK.pack ? " primary" : ""),
      pack.ready ? pack.label : pack.label + " · скоро");
    button.disabled = !pack.ready;
    button.style.minWidth = "190px";
    button.onclick = async () => {
      const res = await api("/api/pack", {pack: pack.id});
      if (!res.ok) return toast(res.note, "bad");
      LOOK.pack = pack.id;
      draw();
      toast("пакет: " + pack.label, "good");
    };
    row.append(button, el("span", "hint grow", pack.about));
    picker.append(row);
  });
  main.append(picker);

  LOOK.fields.forEach((field) => main.append(themeField(field)));
}

async function loadLook() {
  try {
    LOOK = await api("/api/theme");
  } catch (err) {
    LOOK = {fields: [], packs: [], pack: "", engine: {ok: false, note: String(err)}};
  }
  if (TAB === "look") draw();
}

// --------------------------------------------------------------------- posts

let ITEMS = null;          // {items, counts} for the active feed
let ITEM_STATE = "new";
let SWEEP = { running: false, progress: null };

function sweepBar() {
  const bar = el("div", "card");
  const row = el("div", "row");

  const go = el("button", "act primary", SWEEP.running ? "Идёт сбор…" : "Собрать");
  go.disabled = SWEEP.running;
  go.onclick = async () => {
    const res = await api("/api/sweep", {});
    if (!res.ok) return toast(res.note, "bad");
    SWEEP.running = true;
    draw();
    toast("сбор поставлен в очередь", "good");
  };
  row.append(go);

  const line = SWEEP.progress
    ? SWEEP.progress.text + " · " + ago(SWEEP.progress.since)
    : "сбор идёт минутами: сеть ждёт, бот в это время свободен";
  row.append(el("span", "hint grow", line));

  if (ITEMS) {
    [["new", "новые"], ["picked", "взятые"], ["hidden", "скрытые"]].forEach(([id, label]) => {
      const count = ITEMS.counts[id] || 0;
      const button = el("button", "act" + (ITEM_STATE === id ? " primary" : ""),
        label + " " + count);
      button.onclick = () => { ITEM_STATE = id; ITEMS = null; draw(); };
      row.append(button);
    });
  }

  bar.append(row);
  return bar;
}

function itemCard(item) {
  const card = el("div", "card");
  card.dataset.item = String(item.id);

  const head = el("div", "row");
  head.append(el("span", "label", String(Math.round(item.rank || 0))));
  const title = el("span", "grow", item.title || "(без заголовка)");
  title.style.cursor = "pointer";
  title.title = "открыть в браузере";
  title.onclick = () => api("/api/open", { url: item.url });
  head.append(title);
  head.append(el("span", "hint", "r/" + item.source));
  head.append(el("span", "hint", item.age_days + " дн"));
  card.append(head);

  const nums = el("div", "row");
  // The three signals, shown apart rather than only as one number: a post that
  // is hot but dull reads differently from one the model liked.
  nums.append(el("span", "hint", "▲ " + item.score + " · " + pct(item.hot)));
  nums.append(el("span", "hint", "💬 " + item.comments + " · " + pct(item.talk)));
  nums.append(el("span", "hint",
    item.interesting ? "интересность " + item.interesting + "/10" : "не оценён"));
  nums.append(el("span", "hint grow", item.why || ""));
  card.append(nums);

  const line = el("div", "row");
  line.append(el("span", "hint grow", (item.body || "").slice(0, 160)));

  // Treatments are a list, not a button: a second and third kind of write-up
  // are meant to arrive, and they should not each need a new control here.
  (STATE.modes || []).forEach((mode) => {
    const done = (item.made || []).includes(mode.id);
    const button = el("button", "act",
      item.working ? "…" : done ? mode.label + " ✓" : mode.label);
    button.title = mode.about;
    button.disabled = !!item.working;
    button.onclick = async () => {
      if (done) return showTreatment(item, mode);
      await api("/api/treat", { item_id: item.id, mode: mode.id });
      ITEMS = null;
      draw();
      toast(mode.label + ": поставил в очередь", "good");
    };
    line.append(button);
  });

  if ((item.made || []).length) {
    const script = el("button", "act",
      item.scripted ? "Сценарий ✓" : "Сценарий");
    script.title = "разложить пересказ на биты ролика";
    script.disabled = !!item.working;
    script.onclick = async () => {
      if (item.scripted) return showScript(item);
      const res = await api("/api/script", { item_id: item.id });
      if (!res.ok) return toast(res.note, "bad");
      ITEMS = null;
      draw();
      toast("сценарий: поставил в очередь", "good");
    };
    line.append(script);
  }

  if (item.scripted) {
    const voice = el("button", "act", item.voiced ? "Озвучка ✓" : "Озвучить");
    voice.title = "Edge TTS, пословные тайминги";
    voice.disabled = !!item.working;
    voice.onclick = async () => {
      if (item.voiced) return showVoice(item);
      const res = await api("/api/voice", { item_id: item.id });
      if (!res.ok) return toast(res.note, "bad");
      ITEMS = null;
      draw();
      toast("озвучка: поставил в очередь", "good");
    };
    line.append(voice);
  }

  if (item.voiced) {
    const reel = el("button", "act" + (item.reeled ? "" : " primary"),
      item.reeled ? "Ролик ✓" : "Ролик");
    reel.title = "собрать вертикальное видео со звуком";
    reel.disabled = !!item.working;
    reel.onclick = async () => {
      if (item.reeled) return showReel(item);
      const res = await api("/api/render", { item_id: item.id });
      if (!res.ok) return toast(res.note, "bad");
      ITEMS = null;
      draw();
      toast("рендер пошёл — это минуты", "good");
    };
    line.append(reel);
  }

  if (item.state !== "picked") {
    const take = el("button", "act", "Взять");
    take.onclick = async () => {
      await api("/api/items/state", { id: item.id, state: "picked" });
      ITEMS = null;
      draw();
    };
    line.append(take);
  }
  const hide = el("button", "act danger", ITEM_STATE === "hidden" ? "Вернуть" : "Скрыть");
  hide.onclick = async () => {
    await api("/api/items/state",
      { id: item.id, state: ITEM_STATE === "hidden" ? "new" : "hidden" });
    ITEMS = null;
    draw();
  };
  line.append(hide);
  card.append(line);
  return card;
}

function pct(value) {
  return value === null || value === undefined ? "—" : Math.round(value * 100) + "%";
}

async function showReel(item) {
  const made = await api("/api/render?item_id=" + item.id);
  if (!made.found) {
    return toast(made.progress ? made.progress.text : "ещё не готово");
  }

  const card = el("div", "card");
  const head = el("div", "row");
  head.append(el("span", "label", Math.round(made.seconds) + " сек"));
  head.append(el("span", "hint",
    (made.size / 1024 / 1024).toFixed(1) + " МБ · пакет " + made.pack));

  const again = el("button", "act", "Пересобрать");
  again.onclick = async () => {
    await api("/api/render", { item_id: item.id });
    card.remove();
    ITEMS = null;
    draw();
    toast("пересобираю", "good");
  };
  head.append(el("span", "hint grow", ""), again);
  const close = el("button", "act", "Закрыть");
  close.onclick = () => card.remove();
  head.append(close);
  card.append(head);

  // Vertical video in a horizontal panel: cap the height, let it letterbox.
  const player = el("video");
  player.controls = true;
  player.src = "/api/render/file?item_id=" + item.id;
  player.style.cssText = "margin-top:8px;max-height:420px;border-radius:8px;background:#000";
  card.append(player);

  const anchor = [...document.querySelectorAll("#main .card")]
    .find((node) => node.dataset.item === String(item.id));
  if (anchor) anchor.after(card);
  else $("#main").append(card);
}

async function showVoice(item) {
  const made = await api("/api/voice?item_id=" + item.id);
  if (!made.found) return toast("ещё не готово");

  const card = el("div", "card");
  const head = el("div", "row");
  head.append(el("span", "label", Math.round(made.seconds) + " сек"));
  head.append(el("span", "hint", made.words + " слов · " + made.voice));

  // Playing it back is the only honest check of an audio file.
  const player = el("audio");
  player.controls = true;
  player.src = "/api/voice/file?item_id=" + item.id;
  player.style.cssText = "height:34px;flex:1";
  head.append(player);

  const again = el("button", "act", "Заново");
  again.onclick = async () => {
    await api("/api/voice", { item_id: item.id });
    card.remove();
    ITEMS = null;
    draw();
    toast("переозвучиваю", "good");
  };
  head.append(again);
  const close = el("button", "act", "Закрыть");
  close.onclick = () => card.remove();
  head.append(close);
  card.append(head);

  const strip = el("div", "hint");
  strip.style.marginTop = "6px";
  strip.textContent = "первые слова: " +
    made.preview.map((w) => w.text + " " + w.start.toFixed(2)).join(" · ");
  card.append(strip);

  const anchor = [...document.querySelectorAll("#main .card")]
    .find((node) => node.dataset.item === String(item.id));
  if (anchor) anchor.after(card);
  else $("#main").append(card);
}

async function showScript(item) {
  const made = await api("/api/script?item_id=" + item.id);
  if (!made.found) return toast("ещё не готово");

  const card = el("div", "card");
  const head = el("div", "row");
  head.append(el("span", "label", made.beats.length + " битов"));
  head.append(el("span", "hint", "~" + Math.round(made.seconds) + " секунд"));
  head.append(el("span", "hint grow", made.hook));

  const again = el("button", "act", "Заново");
  again.onclick = async () => {
    await api("/api/script", { item_id: item.id });
    card.remove();
    ITEMS = null;
    draw();
    toast("переписываю", "good");
  };
  head.append(again);
  const close = el("button", "act", "Закрыть");
  close.onclick = () => card.remove();
  head.append(close);
  card.append(head);

  made.beats.forEach((beat, index) => {
    const row = el("div", "row");
    row.style.cssText = "align-items:flex-start;margin-top:8px";
    row.append(el("span", "hint", String(index + 1)));

    const column = el("div", "grow");
    // The on-screen line reads without sound, the voice-over is what is said,
    // and the keys are the words a caption can latch onto later.
    const screen = el("div", "label");
    screen.textContent = beat.on_screen;
    const vo = el("div");
    vo.style.cssText = "white-space:pre-wrap;user-select:text;margin-top:2px";
    vo.textContent = beat.vo;
    const under = el("div", "hint");
    under.textContent = beat.seconds + " сек · " + beat.visual +
      (beat.keys.length ? "  ·  ключи: " + beat.keys.join(", ") : "  ·  ключей нет");
    column.append(screen, vo, under);
    row.append(column);
    card.append(row);
  });

  const anchor = [...document.querySelectorAll("#main .card")]
    .find((node) => node.dataset.item === String(item.id));
  if (anchor) anchor.after(card);
  else $("#main").append(card);
}

async function showTreatment(item, mode) {
  const made = await api("/api/treat?item_id=" + item.id + "&mode=" + mode.id);
  if (!made.found) return toast("ещё не готово");

  const card = el("div", "card");
  const head = el("div", "row");
  head.append(el("span", "label", made.title));
  head.append(el("span", "hint grow", mode.label + " · " + made.model));

  const again = el("button", "act", "Заново");
  again.onclick = async () => {
    await api("/api/treat", { item_id: item.id, mode: mode.id });
    card.remove();
    ITEMS = null;
    draw();
    toast("переделываю", "good");
  };
  head.append(again);

  const close = el("button", "act", "Закрыть");
  close.onclick = () => card.remove();
  head.append(close);
  card.append(head);

  const hook = el("div", "hint");
  hook.textContent = made.hook;
  card.append(hook);

  const body = el("div");
  body.style.cssText = "white-space:pre-wrap;margin-top:8px;user-select:text";
  body.textContent = made.text;
  card.append(body);

  card.append(el("div", "hint", made.text.length + " знаков · " +
    Math.round(made.text.length / 15) + " секунд речи"));

  // Right under the post it came from, rather than in a modal: the point is
  // to read them against each other.
  const anchor = [...document.querySelectorAll("#main .card")]
    .find((node) => node.dataset.item === String(item.id));
  if (anchor) anchor.after(card);
  else $("#main").append(card);
}

function drawPosts(main) {
  const feed = (STATE.feeds || []).find((f) => f.active);
  main.append(el("h2", null, "Посты" + (feed ? " · " + feed.name : "")));
  main.append(el("p", "note",
    "Сверху — те, что набрали больше всего по трём сигналам: сколько собрали " +
    "голосов, сколько комментариев и что о них сказала модель."));

  if (!feed) {
    main.append(el("div", "empty", "Сначала заведи ленту."));
    return;
  }
  main.append(sweepBar());

  if (ITEMS === null) {
    main.append(el("div", "empty", "…"));
    loadItems();
    return;
  }
  if (!ITEMS.items.length) {
    main.append(el("div", "empty",
      SWEEP.running ? "Сбор идёт — посты появятся, когда он закончит."
                    : "Пусто. Нажми «Собрать»."));
    return;
  }
  ITEMS.items.forEach((item) => main.append(itemCard(item)));
}

async function loadItems() {
  try {
    ITEMS = await api("/api/items?state=" + ITEM_STATE);
  } catch (err) {
    ITEMS = { items: [], counts: {} };
  }
  if (TAB === "posts") draw();
}

async function pollSweep() {
  try {
    const fresh = await api("/api/sweep");
    const stopped = SWEEP.running && !fresh.running;
    SWEEP = fresh;
    if (stopped) ITEMS = null;  // it just finished; the list is stale
    if (TAB === "posts" && (stopped || fresh.running)) draw();
  } catch (err) {
    /* the offline indicator already covers this */
  }
}

// ---------------------------------------------------------------------- draw

function draw() {
  drawHeader();
  drawNav();
  const main = $("#main");
  main.textContent = "";
  if (TAB === "keys") drawKeys(main);
  else if (TAB === "models") drawModels(main);
  else if (TAB === "sources") drawSources(main);
  else if (TAB === "posts") drawPosts(main);
  else if (TAB === "look") drawLook(main);
  else drawFeeds(main);
}

async function reload() {
  STATE = await api("/api/state");
  draw();
}

reload().catch((err) => {
  document.body.append(el("div", "empty", "панель не отвечает: " + err.message));
});

// The bot picks up a freshly entered token on its own, so the header has to be
// able to change without anyone reloading anything. But redrawing on a timer
// would wipe whatever is being typed — draw() rebuilds every node — so the poll
// only redraws when the answer actually changed, and never mid-keystroke.
async function poll() {
  let fresh;
  try {
    fresh = await api("/api/state");
  } catch (err) {
    if (!OFFLINE) { OFFLINE = true; drawHeader(); }
    return;
  }
  const moved =
    OFFLINE ||
    fresh.bot_running !== STATE.bot_running ||
    fresh.token_pending !== STATE.token_pending;
  OFFLINE = false;
  STATE = fresh;
  const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);
  if (moved && !typing) draw();
}

// Poll while the bot is not up yet (to notice it arriving) and once it is up
// (to notice it leaving). Three seconds either way; the redraw is conditional.
setInterval(() => { poll(); pollSweep(); }, 3000);
