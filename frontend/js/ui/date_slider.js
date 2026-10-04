/**
 * Haqiqiy kuzatuv sanalari bo'yicha slayder va cross-fade o'tishlar.
 */

let datesList = [];
let onDateChangedCallback = null;

export function setupDateSlider(dates, onDateChanged) {
  datesList = dates;
  onDateChangedCallback = onDateChanged;

  const slider = document.getElementById("date-slider");
  const display = document.getElementById("date-display");

  if (!slider || !display) return;

  if (dates.length === 0) {
    slider.disabled = true;
    display.textContent = "Sana mavjud emas";
    return;
  }

  slider.disabled = false;
  slider.min = "0";
  slider.max = (dates.length - 1).toString();
  slider.value = (dates.length - 1).toString(); // Eng oxirgi sana
  display.textContent = dates[dates.length - 1].label;

  slider.oninput = (e) => {
    const idx = parseInt(e.target.value, 10);
    const selected = datesList[idx];
    if (selected) {
      display.textContent = selected.label;
      if (onDateChangedCallback) onDateChangedCallback(selected);
    }
  };
}
