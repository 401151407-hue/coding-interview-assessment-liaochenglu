import { clampQuantity } from "../domain/variants";

export interface QuantityStepperProps {
  value: number;
  /** Highest allowed value: the selected SKU's available quantity. */
  max: number;
  disabled?: boolean;
  onChange: (next: number) => void;
}

export function QuantityStepper({
  value,
  max,
  disabled = false,
  onChange,
}: QuantityStepperProps) {
  const ceiling = Math.max(max, 1);
  const isDisabled = disabled || max < 1;

  return (
    <div className="stepper" role="group" aria-label="Quantity">
      <button
        type="button"
        className="stepper__button"
        onClick={() => onChange(clampQuantity(value - 1, ceiling))}
        disabled={isDisabled || value <= 1}
        aria-label="Decrease quantity"
      >
        &minus;
      </button>
      <input
        className="stepper__input"
        type="number"
        inputMode="numeric"
        min={1}
        max={ceiling}
        step={1}
        value={value}
        disabled={isDisabled}
        aria-label="Quantity"
        onChange={(event) => {
          const parsed = Number.parseInt(event.target.value, 10);
          onChange(Number.isNaN(parsed) ? 1 : clampQuantity(parsed, ceiling));
        }}
      />
      <button
        type="button"
        className="stepper__button"
        onClick={() => onChange(clampQuantity(value + 1, ceiling))}
        disabled={isDisabled || value >= ceiling}
        aria-label="Increase quantity"
      >
        +
      </button>
    </div>
  );
}
