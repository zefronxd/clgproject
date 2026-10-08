const chartDataElement = document.querySelector("#chart-data");
if (chartDataElement && window.Chart) {
  const data = JSON.parse(chartDataElement.textContent);
  const emotionColors = {
    anger: "#d98575",
    disgust: "#94a879",
    fear: "#8494be",
    joy: "#e5b65d",
    neutral: "#8da99d",
    sadness: "#7896b5",
    surprise: "#c38fb6",
  };
  const labels = Object.keys(data.emotions);
  const values = labels.map((emotion) => data.emotions[emotion]);

  const trendCanvas = document.querySelector("#sentiment-chart");
  if (trendCanvas) {
    new Chart(trendCanvas, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [{
          data: data.averages,
          borderColor: "#6d9b86",
          backgroundColor: "rgba(109, 155, 134, .13)",
          pointBackgroundColor: "#6d9b86",
          pointBorderColor: "#f8fbf8",
          pointBorderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2.5,
          tension: 0.34,
          spanGaps: true,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#244437",
            padding: 10,
            displayColors: false,
            callbacks: {
              label: (item) => item.raw === null ? "No entry" : `Sentiment ${Number(item.raw).toFixed(2)}`,
            },
          },
        },
        scales: {
          y: {
            min: -1,
            max: 1,
            grid: { color: "rgba(61, 86, 74, .08)" },
            border: { display: false },
            ticks: {
              stepSize: 0.5,
              color: "#84928a",
              font: { family: "DM Sans", size: 10 },
              callback: (value) => value > 0 ? `+${value}` : value,
            },
          },
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: {
              color: "#84928a",
              maxTicksLimit: 7,
              maxRotation: 0,
              font: { family: "DM Sans", size: 10 },
            },
          },
        },
      },
    });
  }

  const emotionCanvas = document.querySelector("#emotion-chart");
  if (emotionCanvas) {
    new Chart(emotionCanvas, {
      type: "doughnut",
      data: {
        labels: labels.map((item) => item.charAt(0).toUpperCase() + item.slice(1)),
        datasets: [{
          data: values,
          backgroundColor: labels.map((emotion) => emotionColors[emotion]),
          borderColor: "#fff",
          borderWidth: 4,
          hoverOffset: 5,
        }],
      },
      options: {
        cutout: "73%",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#244437",
            padding: 10,
            callbacks: { label: (item) => `${item.label}: ${item.raw}` },
          },
        },
      },
    });
  }

  const legend = document.querySelector("#emotion-legend");
  if (legend) {
    labels.forEach((emotion) => {
      const row = document.createElement("div");
      row.className = "legend-row";
      const swatch = document.createElement("span");
      swatch.className = "legend-swatch";
      swatch.style.backgroundColor = emotionColors[emotion];
      const name = document.createElement("span");
      name.textContent = emotion.charAt(0).toUpperCase() + emotion.slice(1);
      const count = document.createElement("strong");
      count.textContent = data.emotions[emotion];
      row.append(swatch, name, count);
      legend.append(row);
    });
  }
}
