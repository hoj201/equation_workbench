// MathJax helpers shared by both tabs.

const mathReady = new Promise((resolve) => {
  const wait = () => (window.MathJax?.startup?.promise ? MathJax.startup.promise.then(resolve) : setTimeout(wait, 30));
  wait();
});

export async function renderMath(el, latex, display = true) {
  await mathReady;
  el.replaceChildren(MathJax.tex2chtml(latex, { display }));
  MathJax.startup.document.clear();
  MathJax.startup.document.updateDocument();
}
