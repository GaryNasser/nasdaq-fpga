// tb_parse_rate: can itch_parse actually accept a byte every cycle?
//
// The full chain loses 19139 of 1237116 bytes, but neither module fails alone.
// The distinguishing factor is rate: mold64_reasm can emit one byte per cycle
// continuously, while tb_book's testbench deasserts TVALID between bytes.
//
// This feeds the SAME byte stream to itch_parse at three rates and compares the
// message count. If message counts differ by rate, the parser has a rate
// dependency - which is a real defect, because AXI-Stream permits back-to-back
// beats.
`timescale 1ns / 1ps

module tb_parse_rate;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg  [4:0]  p_awaddr = 0;
  reg         p_awvalid = 0;
  wire        p_awready;
  reg  [31:0] p_wdata = 0;
  reg         p_wvalid = 0;
  wire        p_wready;
  wire [1:0]  p_bresp;
  wire        p_bvalid;
  reg         p_bready = 1;
  reg  [4:0]  p_araddr = 0;
  reg         p_arvalid = 0;
  wire        p_arready;
  wire [31:0] p_rdata;
  wire [1:0]  p_rresp;
  wire        p_rvalid;
  reg         p_rready = 1;

  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'h01;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  wire [255:0] evt;
  wire         evt_valid;
  wire         evt_ready;
  wire [15:0]  stock_locate;
  wire         ts_in_valid;

  itch_parse ip (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(p_awaddr), .s_axi_awvalid(p_awvalid),
    .s_axi_awready(p_awready), .s_axi_wdata(p_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(p_wvalid),
    .s_axi_wready(p_wready), .s_axi_bresp(p_bresp),
    .s_axi_bvalid(p_bvalid), .s_axi_bready(p_bready),
    .s_axi_araddr(p_araddr), .s_axi_arvalid(p_arvalid),
    .s_axi_arready(p_arready), .s_axi_rdata(p_rdata),
    .s_axi_rresp(p_rresp), .s_axi_rvalid(p_rvalid),
    .s_axi_rready(p_rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .evt(evt), .evt_valid(evt_valid), .evt_ready(evt_ready),
    .stock_locate(stock_locate),
    .ts_in_valid(ts_in_valid)
  );

  // Event counter (sink always ready).
  assign evt_ready = 1'b1;
  integer evt_n;
  initial evt_n = 0;
  always @(posedge aclk) if (aresetn && evt_valid && evt_ready) evt_n = evt_n + 1;

  parameter MAXB   = 1300000;
  parameter NPKT   = 850;
  parameter GAPCYC = 0;      // idle cycles between bytes; 0 = back-to-back

  reg [7:0] img [0:MAXB-1];
  integer   pkt_off [0:NPKT-1];
  integer   pkt_len [0:NPKT-1];
  integer   k, p, off, cnt, m, mlen, q;

  task ip_write(input [4:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      p_awaddr <= a; p_awvalid <= 1; p_wdata <= v; p_wvalid <= 1;
      while (!(p_awready && p_wready)) @(negedge aclk);
      @(negedge aclk);
      p_awvalid <= 0; p_wvalid <= 0;
      while (!p_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  // Send the message stream byte by byte, with an optional idle cycle between
  // handshakes. TLAST on the final body byte of each message.
  task send_stream;
    integer pp, c2, mm, ml2, qb, nb;
    reg [7:0] mbuf [0:1300000];
    reg       mlast [0:1300000];
    begin
      nb = 0;
      for (pp = 0; pp < NPKT; pp = pp + 1) begin
        c2 = {img[pkt_off[pp]+10], img[pkt_off[pp]+11]};
        mm = pkt_off[pp] + 12;
        for (k = 0; k < c2; k = k + 1) begin
          ml2 = {img[mm], img[mm+1]};
          mbuf[nb] = img[mm];   mlast[nb] = 1'b0; nb = nb + 1;
          mbuf[nb] = img[mm+1]; mlast[nb] = 1'b0; nb = nb + 1;
          for (qb = 0; qb < ml2; qb = qb + 1) begin
            mbuf[nb] = img[mm + 2 + qb];
            mlast[nb] = (qb == (ml2 - 1));
            nb = nb + 1;
          end
          mm = mm + 2 + ml2;
        end
      end
      qb = 0;
      while (qb < nb) begin
        if (GAPCYC > 0) begin
          s_axis_tvalid <= 0;
          repeat (GAPCYC) @(negedge aclk);
        end
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= {56'd0, mbuf[qb]};
        s_axis_tlast  <= mlast[qb];
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        qb = qb + 1;
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
      s_axis_tlast  <= 0;
    end
  endtask

  initial begin
    $readmemh("img.hex", img);
    off = 0;
    for (p = 0; p < NPKT; p = p + 1) begin
      pkt_off[p] = off;
      cnt = {img[off+10], img[off+11]};
      m = off + 12;
      for (k = 0; k < cnt; k = k + 1) begin
        mlen = {img[m], img[m+1]};
        m = m + 2 + mlen;
      end
      pkt_len[p] = m - off;
      off = m;
    end

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    ip_write(5'h14, 32'h1);
    repeat (4) @(negedge aclk);

    send_stream;
    repeat (200000) @(negedge aclk);

    $display("PARSE-RATE gapcyc=%0d events=%0d (expected 43428)",
             GAPCYC, evt_n);
    if (evt_n == 43428) $display("PARSE-RATE-PASS");
    else                $display("PARSE-RATE-FAIL");
    $finish;
  end

endmodule
