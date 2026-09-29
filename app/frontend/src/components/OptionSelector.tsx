/**
 * One option dimension rendered as a native radio group.
 *
 * Native inputs are used deliberately: they already provide arrow-key roving
 * focus, grouping, label association and "1 of 3" announcements. Re-implementing
 * that with `div[role=radio]` is the usual source of broken keyboard support.
 */

import type { Product, ProductOption } from "../api/types";
import type { Selection } from "../domain/variants";
import { reportOptionValues } from "../domain/variants";

export interface OptionSelectorProps {
  product: Product;
  option: ProductOption;
  selection: Selection;
  /** Unique prefix for input ids, so several PDPs can coexist on one page. */
  groupId: string;
  disabled?: boolean;
  onSelect: (optionId: string, valueId: string) => void;
}

export function OptionSelector({
  product,
  option,
  selection,
  groupId,
  disabled = false,
  onSelect,
}: OptionSelectorProps) {
  const states = new Map(
    reportOptionValues(product, selection, option.id).map((report) => [
      report.id,
      report.state,
    ]),
  );
  const selectedValueId = selection[option.id];
  const selectedLabel = option.values.find(
    (value) => value.id === selectedValueId,
  )?.label;

  return (
    <fieldset className="option" disabled={disabled}>
      <legend className="option__legend">
        <span className="option__name">{option.label}</span>
        <span className="option__chosen">
          {selectedLabel ?? `Select ${option.label.toLowerCase()}`}
        </span>
      </legend>

      <div className="option__values">
        {option.values.map((value) => {
          const state = states.get(value.id) ?? "unavailable";
          const inputId = `${groupId}-${option.id}-${value.id}`;
          const isSelected = selectedValueId === value.id;

          const controlClasses = ["option__control"];
          if (isSelected) controlClasses.push("option__control--selected");
          if (state === "unavailable") {
            controlClasses.push("option__control--unavailable");
          }
          if (state === "out-of-stock") {
            controlClasses.push("option__control--out-of-stock");
          }

          return (
            <div className="option__item" key={value.id}>
              <input
                className="option__input"
                type="radio"
                id={inputId}
                name={`${groupId}-${option.id}`}
                value={value.id}
                checked={isSelected}
                disabled={state === "unavailable" || disabled}
                onChange={() => onSelect(option.id, value.id)}
              />
              <label className={controlClasses.join(" ")} htmlFor={inputId}>
                {option.id === "color" ? (
                  <span
                    className="swatch"
                    style={{ backgroundColor: value.swatch }}
                    aria-hidden="true"
                  />
                ) : null}
                <span className="option__text">{value.label}</span>
                {state === "out-of-stock" ? (
                  <span className="option__flag">Sold out</span>
                ) : null}
                {state === "unavailable" ? (
                  <span className="sr-only">
                    {" "}
                    (not available with the current selection)
                  </span>
                ) : null}
              </label>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
