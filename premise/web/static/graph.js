import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11.12.1/dist/mermaid.esm.min.mjs';

// Dependency graphs in the darkfield palette; state colours come from classDefs the server appends.
mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'strict',
  theme: 'base',
  themeVariables: {
    darkMode: true,
    background: '#161411',
    mainBkg: '#1e1b17',
    primaryColor: '#1e1b17',
    primaryTextColor: '#ece3cf',
    primaryBorderColor: '#6b6252',
    nodeBorder: '#6b6252',
    nodeTextColor: '#ece3cf',
    secondaryColor: '#1e1b17',
    tertiaryColor: '#161411',
    lineColor: '#9b917d',
    edgeLabelBackground: '#161411',
    clusterBkg: '#161411',
    fontFamily: 'Schibsted Grotesk, Segoe UI, system-ui, sans-serif',
    fontSize: '14px',
  },
  flowchart: {curve: 'basis', nodeSpacing: 36, rankSpacing: 64, padding: 14, useMaxWidth: false},
});

const graphs = document.querySelectorAll('pre.mermaid');
// On narrow screens the same chains read top-down instead of overflowing sideways.
if (innerWidth < 700) graphs.forEach(pre => { pre.textContent = pre.textContent.replace(/^\s*flowchart LR/, 'flowchart TD'); });
if (graphs.length) mermaid.run({nodes: [...graphs]}).then(() => {
  // A graph wider than its panel scrolls; fade the far edge so that reads as more, not as cut off.
  for (const pre of graphs) if (pre.scrollWidth > pre.clientWidth + 4) pre.classList.add('scrolls');
});

export default mermaid;
