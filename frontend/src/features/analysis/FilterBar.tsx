import { useMemo, useRef, useState } from "react";
import { IconFilter, IconPlus, IconX } from "@/app/icons";
import { Button, Input, Select, cx } from "@/shared/ui/ui";
import type { Filter } from "../dashboards/useDashboardData";
import { FieldInfo, fmtVal, useOutside, useValues } from "./hooks";
import { AFilter, OP_LABEL, describeValue } from "./state";

const OPS: Record<string, [Filter["op"], string][]> = {
  string: [["in", "é"], ["neq", "não é"], ["contains", "contém"]],
  number: [["between", "entre"], ["gte", "maior ou igual a"], ["lte", "menor ou igual a"]],
  date: [["between", "entre"]],
  boolean: [["eq", "é"]],
};
const kind = (t: string) => (t === "integer" || t === "decimal" ? "number" : t === "date" || t === "datetime" ? "date" : t === "boolean" ? "boolean" : "string");

function ValuePicker({ id, field, multi, selected, onChange }: { id: string; field: FieldInfo; multi: boolean; selected: string[]; onChange: (v: string[]) => void }) {
  const [q, setQ] = useState("");
  const vals = useValues(id, field.datasetIds[0], field.name, q);
  const list = vals.data?.values ?? [];
  const toggle = (v: string) => onChange(multi ? (selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]) : [v]);
  return (
    <div>
      <Input autoFocus placeholder={`Buscar ${field.label.toLowerCase()}…`} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar valor"
        onKeyDown={(e) => { if (e.key === "Enter" && q.trim()) { e.preventDefault(); toggle(q.trim()); setQ(""); } }} />
      <ul className={cx("an-list mt-2 max-h-52 overflow-y-auto", vals.isFetching && "opacity-60")} role="listbox" aria-label="Valores" aria-multiselectable={multi}>
        {list.map((v, i) => {
          const on = selected.includes(v.value);
          return (
            <li key={v.value} role="option" aria-selected={on} style={{ "--i": Math.min(i, 10) } as React.CSSProperties}>
              <button type="button" className={cx("an-opt", on && "is-on")} onClick={() => toggle(v.value)}>
                <span className="an-check" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-left">{v.value}</span>
                <span className="tabular text-xs text-ink-mute">{v.count}</span>
              </button>
            </li>
          );
        })}
        {!vals.isLoading && list.length === 0 && <li className="px-2 py-3 text-center text-sm text-ink-mute">{q ? "Nada encontrado. Enter usa o texto digitado." : "Sem valores."}</li>}
      </ul>
    </div>
  );
}

export function FilterEditor({ id, fields, initial, presetField, onSubmit, onCancel }: {
  id: string; fields: Map<string, FieldInfo>; initial?: AFilter; presetField?: string; onSubmit: (f: AFilter) => void; onCancel: () => void;
}) {
  const list = useMemo(() => [...fields.values()].sort((a, b) => a.label.localeCompare(b.label, "pt-BR")), [fields]);
  const [name, setName] = useState(initial?.field ?? presetField ?? list.find((f) => f.data_type === "string")?.name ?? list[0]?.name ?? "");
  const field = fields.get(name);
  const k = field ? kind(field.data_type) : "string";
  const ops = OPS[k];
  const [op, setOp] = useState<Filter["op"]>(initial?.op === "eq" && k === "string" ? "in" : initial?.op ?? ops[0][0]);
  const asList = (v: unknown) => (Array.isArray(v) ? v.map(String) : v == null ? [] : [String(v)]);
  const [vals, setVals] = useState<string[]>(initial ? asList(initial.value) : []);
  const [a, setA] = useState(initial && Array.isArray(initial.value) ? String(initial.value[0] ?? "") : initial && !Array.isArray(initial.value) ? String(initial.value ?? "") : "");
  const [b, setB] = useState(initial && Array.isArray(initial.value) ? String(initial.value[1] ?? "") : "");
  const [bool, setBool] = useState<"true" | "false">(initial?.value === false ? "false" : "true");
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, onCancel);

  const changeField = (n: string) => { setName(n); const nk = kind(fields.get(n)?.data_type ?? "string"); setOp(OPS[nk][0][0]); setVals([]); setA(""); setB(""); };
  const num = (s: string) => (s.trim() === "" || Number.isNaN(Number(s)) ? null : Number(s));
  let value: unknown = null; let ok = false;
  if (k === "string" && op === "contains") { value = a.trim(); ok = !!a.trim(); }
  else if (k === "string") { value = op === "neq" ? vals[0] : vals; ok = vals.length > 0; }
  else if (k === "boolean") { value = bool === "true"; ok = true; }
  else if (op === "between") { value = k === "number" ? [num(a), num(b)] : [a, b]; ok = k === "number" ? num(a) != null && num(b) != null : !!a && !!b && a <= b; }
  else { value = k === "number" ? num(a) : a; ok = value != null && value !== ""; }

  return (
    <div ref={ref} role="dialog" aria-label={initial ? "Editar filtro" : "Novo filtro"} className="an-pop left-0 top-[calc(100%+8px)] w-[22rem] space-y-3 p-4">
      <label className="block text-xs font-semibold text-ink-mute">Campo
        <Select className="mt-1" value={name} onChange={(e) => changeField(e.target.value)}>{list.map((f) => <option key={f.name} value={f.name}>{f.label}</option>)}</Select>
      </label>
      {k !== "boolean" && (
        <label className="block text-xs font-semibold text-ink-mute">Condição
          <Select className="mt-1" value={op} onChange={(e) => { setOp(e.target.value as Filter["op"]); setVals((v) => v.slice(0, 1)); }}>{ops.map(([o, l]) => <option key={o} value={o}>{l}</option>)}</Select>
        </label>
      )}
      <div key={`${name}-${op}`} className="an-swap">
        {k === "string" && op !== "contains" && field && <ValuePicker id={id} field={field} multi={op === "in"} selected={vals} onChange={setVals} />}
        {k === "string" && op === "contains" && <Input autoFocus aria-label="Texto" placeholder="Parte do texto" value={a} onChange={(e) => setA(e.target.value)} />}
        {k === "boolean" && <Select aria-label="Valor" value={bool} onChange={(e) => setBool(e.target.value as "true" | "false")}><option value="true">Sim</option><option value="false">Não</option></Select>}
        {(k === "number" || k === "date") && (
          <div className={cx("grid gap-2", op === "between" ? "grid-cols-2" : "grid-cols-1")}>
            <Input aria-label={op === "between" ? "De" : "Valor"} type={k === "number" ? "number" : "date"} value={a} onChange={(e) => setA(e.target.value)} />
            {op === "between" && <Input aria-label="Até" type={k === "number" ? "number" : "date"} value={b} onChange={(e) => setB(e.target.value)} />}
          </div>
        )}
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <Button variant="ghost" size="sm" onClick={onCancel}>Cancelar</Button>
        <Button size="sm" disabled={!ok || !field} onClick={() => onSubmit({ field: name, op, value, src: "manual" })}>{initial ? "Salvar" : "Aplicar"}</Button>
      </div>
    </div>
  );
}

/** Chips editaveis dos filtros manuais (o drill fica no breadcrumb). */
export function FilterBar({ id, filters, fields, onChange, adding, onAddingChange, presetField }: {
  id: string; filters: AFilter[]; fields: Map<string, FieldInfo>; onChange: (f: AFilter[]) => void;
  adding: boolean; onAddingChange: (v: boolean) => void; presetField?: string;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [leaving, setLeaving] = useState<string | null>(null);
  const manual = filters.map((f, i) => ({ f, i })).filter(({ f }) => f.src === "manual");
  const key = (f: AFilter) => `${f.field}|${f.op}|${JSON.stringify(f.value)}`;
  const remove = (i: number) => { setLeaving(key(filters[i])); setTimeout(() => { onChange(filters.filter((_, j) => j !== i)); setLeaving(null); }, 170); };
  const canAdd = fields.size > 0;
  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Filtros">
      {manual.map(({ f, i }) => (
        <div key={key(f)} data-anchor className={cx("relative", leaving === key(f) && "an-chip-out")}>
          <span className="an-chip">
            <button type="button" className="an-chip-main" aria-label={`Editar filtro ${fields.get(f.field)?.label ?? f.field}`} onClick={() => { setEditing(editing === i ? null : i); onAddingChange(false); }}>
              <span className="text-ink-mute">{fields.get(f.field)?.label ?? f.field}</span>
              <span className="text-ink-mute">{OP_LABEL[f.op] ?? f.op}</span>
              <strong className="max-w-[16rem] truncate">{describeValue(f, fmtVal)}</strong>
            </button>
            <button type="button" className="an-chip-x" aria-label={`Remover filtro ${fields.get(f.field)?.label ?? f.field}`} onClick={() => remove(i)}><IconX /></button>
          </span>
          {editing === i && <FilterEditor id={id} fields={fields} initial={f} onCancel={() => setEditing(null)} onSubmit={(nf) => { onChange(filters.map((x, j) => (j === i ? nf : x))); setEditing(null); }} />}
        </div>
      ))}
      <div className="relative" data-anchor>
        <button type="button" className="an-add" disabled={!canAdd} aria-expanded={adding} aria-haspopup="dialog" onClick={() => { onAddingChange(!adding); setEditing(null); }}>
          {manual.length === 0 ? <IconFilter /> : <IconPlus width={14} height={14} />}{manual.length === 0 ? "Adicionar filtro" : "Filtro"}
        </button>
        {adding && <FilterEditor id={id} fields={fields} presetField={presetField} onCancel={() => onAddingChange(false)} onSubmit={(nf) => { onChange([...filters, nf].slice(0, 20)); onAddingChange(false); }} />}
      </div>
    </div>
  );
}
