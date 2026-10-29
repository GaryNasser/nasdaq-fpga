// tb_gls: gate-level verification of the synthesised mold64_reasm.
//
// The RTL suites drive behavioural RTL. This drives the actual gate netlist
// produced by Vivado for the module, using the real capture, and checks the
// design purely as a black box by comparing the emitted M_AXIS byte stream
// against the bytes the capture says should come out.
//
// That is a stronger contract than counting: the module must emit, for every
// MoldUDP64 message in the file, the 2-byte length prefix followed by the body,
// in order and byte for byte.
`timescale 1ns / 1ps

module tb_gls;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg  [4:0]  s_axi_awaddr = 0;
  reg  [2:0]  s_axi_awprot = 0;
  reg         s_axi_awvalid = 0;
  wire        s_axi_awready;
  reg  [31:0] s_axi_wdata = 0;
  reg  [3:0]  s_axi_wstrb = 4'hF;
  reg         s_axi_wvalid = 0;
  wire        s_axi_wready;
  wire [1:0]  s_axi_bresp;
  wire        s_axi_bvalid;
  reg         s_axi_bready = 1;
  reg  [4:0]  s_axi_araddr = 0;
  reg  [2:0]  s_axi_arprot = 0;
  reg         s_axi_arvalid = 0;
  wire        s_axi_arready;
  wire [31:0] s_axi_rdata;
  wire [1:0]  s_axi_rresp;
  wire        s_axi_rvalid;
  reg         s_axi_rready = 1;

  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'hFF;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  wire [7:0]  m_axis_tdata;
  wire        m_axis_tvalid;
  reg         m_axis_tready = 1;

  mold64_reasm dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(s_axi_awaddr), .s_axi_awprot(s_axi_awprot),
    .s_axi_awvalid(s_axi_awvalid), .s_axi_awready(s_axi_awready),
    .s_axi_wdata(s_axi_wdata), .s_axi_wstrb(s_axi_wstrb),
    .s_axi_wvalid(s_axi_wvalid), .s_axi_wready(s_axi_wready),
    .s_axi_bresp(s_axi_bresp), .s_axi_bvalid(s_axi_bvalid),
    .s_axi_bready(s_axi_bready),
    .s_axi_araddr(s_axi_araddr), .s_axi_arprot(s_axi_arprot),
    .s_axi_arvalid(s_axi_arvalid), .s_axi_arready(s_axi_arready),
    .s_axi_rdata(s_axi_rdata), .s_axi_rresp(s_axi_rresp),
    .s_axi_rvalid(s_axi_rvalid), .s_axi_rready(s_axi_rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready)
  );

  parameter MAXB        = 1300000;
  parameter NPKT        = 850;
  parameter TOTAL_BYTES = 1237116;
  parameter EXPOUT      = 1700000;

  reg [7:0] img [0:MAXB-1];
  integer   pkt_off [0:NPKT-1];
  integer   pkt_len [0:NPKT-1];

  // Expected emitted stream: each message as 2-byte length + body.
  reg [7:0] exp_stream [0:EXPOUT-1];
  integer   exp_bytes;

  integer k, p, off, cnt, m, mlen, q;

  // Observed stream.
  integer out_bytes;
  integer out_mismatch;
  integer first_bad;
  initial begin
    out_bytes = 0; out_mismatch = 0; first_bad = -1;
  end

  always @(posedge aclk) begin
    if (aresetn && m_axis_tvalid && m_axis_tready) begin
      if (out_bytes < EXPOUT) begin
        if (exp_stream[out_bytes] !== m_axis_tdata) begin
          out_mismatch = out_mismatch + 1;
          if (first_bad < 0) begin
            first_bad = out_bytes;
            $display("  FIRST-BAD byte %0d got=%02h want=%02h",
                     out_bytes, m_axis_tdata, exp_stream[out_bytes]);
          end
        end
      end
      out_bytes = out_bytes + 1;
    end
  end

  task axi_write(input [4:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      s_axi_awaddr <= a; s_axi_awvalid <= 1;
      s_axi_wdata  <= v; s_axi_wvalid  <= 1;
      while (!(s_axi_awready && s_axi_wready)) @(negedge aclk);
      @(negedge aclk);
      s_axi_awvalid <= 0; s_axi_wvalid <= 0;
      while (!s_axi_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task send_pkt(input integer idx);
    integer done, base, len;
    reg [63:0] wv;
    begin
      base = pkt_off[idx];
      len  = pkt_len[idx];
      q = 0;
      while (q < len) begin
        done = (len - q) < 8 ? (len - q) : 8;
        for (k = 0; k < 8; k = k + 1)
          wv[k*8 +: 8] = (k < done) ? img[base + q + k] : 8'h00;
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= wv;
        s_axis_tkeep  <= (done == 8) ? 8'hFF : ((8'hFF >> (8 - done)));
        s_axis_tlast  <= ((q + done) == len);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        q = q + done;
      end
    end
  endtask

  initial begin
    $readmemh("img.hex", img);

    // Packet boundaries from the MoldUDP64 framing, and the expected output
    // stream built from the same bytes.
    off = 0;
    exp_bytes = 0;
    for (p = 0; p < NPKT; p = p + 1) begin
      pkt_off[p] = off;
      cnt = {img[off+10], img[off+11]};
      m = off + 12;
      for (k = 0; k < cnt; k = k + 1) begin
        mlen = {img[m], img[m+1]};
        exp_stream[exp_bytes] = img[m];     exp_bytes = exp_bytes + 1;
        exp_stream[exp_bytes] = img[m+1];   exp_bytes = exp_bytes + 1;
        for (q = 0; q < mlen; q = q + 1) begin
          exp_stream[exp_bytes] = img[m + 2 + q];
          exp_bytes = exp_bytes + 1;
        end
        m = m + 2 + mlen;
      end
      pkt_len[p] = m - off;
      off = m;
    end
    $display("SCAN packets=%0d consumed=%0d expected=%0d expout=%0d",
             NPKT, off, TOTAL_BYTES, exp_bytes);

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    for (p = 0; p < NPKT; p = p + 1)
      send_pkt(p);

    @(negedge aclk);
    s_axis_tvalid <= 0;
    s_axis_tlast  <= 0;

    repeat (4000000) @(negedge aclk);

    $display("GLS out_bytes=%0d exp_bytes=%0d mismatches=%0d first_bad=%0d",
             out_bytes, exp_bytes, out_mismatch, first_bad);
    if (out_bytes == exp_bytes && out_mismatch == 0 && first_bad < 0)
      $display("GLS-PASS");
    else
      $display("GLS-FAIL");
    $finish;
  end

endmodule
