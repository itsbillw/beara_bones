/* Form column: last 6 results as colored circles (W=green, D=grey, L=red). Oldest left, newest right. */
var dagcomponentfuncs = (window.dashAgGridComponentFunctions =
  window.dashAgGridComponentFunctions || {});

dagcomponentfuncs.FormCellRenderer = function (props) {
  var value = props.value || "";
  var letters = value.split("");
  var colors = { W: "#22c55e", D: "#6b7280", L: "#ef4444" };
  return React.createElement(
    "div",
    {
      style: {
        display: "flex",
        height: "100%",
        alignItems: "center",
        gap: "3px",
        flexWrap: "wrap",
      },
    },
    letters.map(function (l, i) {
      return React.createElement(
        "span",
        {
          key: i,
          style: {
            width: "20px",
            height: "20px",
            borderRadius: "50%",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "11px",
            fontWeight: "bold",
            color: "#fff",
            background: colors[l] || "#9ca3af",
          },
        },
        l,
      );
    }),
  );
};
