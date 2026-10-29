// tb_parity: compare EVERY byte the parser consumes against the exact stream.
//
// The parser desynchronises after ~6 packets on a 89-packet stream while the
// RAM is provably intact at the start. This finds the precise byte position
// where what the parser reads stops matching what was sent, and prints the
// RAM word involved so a wrong-store can be told apart from a wrong-read.
`timescale 1ns / 1ps

module tb_parity;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg  [4:0]  s_axi_awaddr = 0;
  reg         s_axi_awvalid = 0;
  wire        s_axi_awready;
  reg  [31:0] s_axi_wdata = 0;
  reg         s_axi_wvalid = 0;
  wire        s_axi_wready;
  wire [1:0]  s_axi_bresp;
  wire        s_axi_bvalid;
  reg         s_axi_bready = 1;
  reg  [4:0]  s_axi_araddr = 0;
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

  mold64_reasm #(.SESSION(64'h4E41534441513031)) dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(s_axi_awaddr), .s_axi_awvalid(s_axi_awvalid),
    .s_axi_awready(s_axi_awready), .s_axi_wdata(s_axi_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(s_axi_wvalid),
    .s_axi_wready(s_axi_wready), .s_axi_bresp(s_axi_bresp),
    .s_axi_bvalid(s_axi_bvalid), .s_axi_bready(s_axi_bready),
    .s_axi_araddr(s_axi_araddr), .s_axi_arvalid(s_axi_arvalid),
    .s_axi_arready(s_axi_arready), .s_axi_rdata(s_axi_rdata),
    .s_axi_rresp(s_axi_rresp), .s_axi_rvalid(s_axi_rvalid),
    .s_axi_rready(s_axi_rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready)
  );

  integer i, k, npkt;
  parameter NPKT      = 89;
  parameter MSG_LEN   = 36;
  parameter PKT_BYTES = 50;

  // The full expected byte stream, uniformly accessible by (wrapped) index.
  reg [7:0] exp_stream [0:8191];

  reg [7:0] pktbuf [0:PKT_BYTES-1];
  reg [7:0] d;
  integer b;
  integer nerr;
  integer ef;

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

  // The authoritative check: every time pkt_rd_ptr advances, the byte the FSM
  // latched at the old position must equal the expected stream byte there.
  integer parity_errs;
  integer first_bad;
  integer wrap_base;
  integer abs_consumed;
  reg [11:0] rd_seen;
  reg [7:0]           byte_seen;
  reg                 armed;
  reg                 started;
  reg                 ready;

  initial begin
    parity_errs = 0;
    first_bad = -1;
    rd_seen = 12'd0;
    wrap_base = 0;
    abs_consumed = 0;
    armed = 0;
    started = 0;
    ready = 0;
  end

  always @(posedge aclk) begin
    if (aresetn) begin
      if (ready && armed && (rd_seen < 12'd4095) && (dut.pkt_rd_ptr != rd_seen)) begin
        if (byte_seen !== exp_stream[rd_seen[12:0] + wrap_base]) begin
          parity_errs = parity_errs + 1;
          if (parity_errs == 1) first_bad = rd_seen + wrap_base;
          if (parity_errs == 1)
            $display("PARITY rdseen=%0d wrap=%0d idx=%0d got=%h want=%h n=%0d",
                     rd_seen, wrap_base, rd_seen + wrap_base, byte_seen,
                     exp_stream[rd_seen + wrap_base], parity_errs);
        end
        if (dut.pkt_rd_ptr == 12'd0 && rd_seen != 12'd0) wrap_base = wrap_base + 4096;
        rd_seen <= dut.pkt_rd_ptr;
      end else if (!armed) begin
        rd_seen <= dut.pkt_rd_ptr;
      end
      if (started && dut.fifo_not_empty_live) armed <= 1;
      byte_seen <= dut.cur_byte;
      // cur_byte is the byte at pkt_rd_ptr; when rd advances next cycle
    end
  end

  task build_pkt(input [15:0] sq);
    begin
      pktbuf[0]=8'h4E; pktbuf[1]=8'h41; pktbuf[2]=8'h53; pktbuf[3]=8'h44;
      pktbuf[4]=8'h41; pktbuf[5]=8'h51; pktbuf[6]=8'h30; pktbuf[7]=8'h31;
      pktbuf[8]=sq[15:8]; pktbuf[9]=sq[7:0];
      pktbuf[10]=8'h00; pktbuf[11]=8'h01;
      pktbuf[12]=8'h00; pktbuf[13]=MSG_LEN[7:0];
      for (k = 0; k < MSG_LEN; k = k + 1)
        pktbuf[14+k] = (k == 0) ? 8'h41 : (8'h00 | k[7:0]);
    end
  endtask

  task send_built;
    reg [63:0] w;
    begin
      b = 0;
      while (b < PKT_BYTES) begin
        for (k = 0; k < 8; k = k + 1)
          w[k*8 +: 8] = ((b + k) < PKT_BYTES) ? pktbuf[b + k] : 8'h00;
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= w;
        if ((b + 8) > PKT_BYTES) begin
          s_axis_tkeep <= (8'hFF >> (8 - (PKT_BYTES - b)));
          s_axis_tlast <= 1'b1;
        end else begin
          s_axis_tkeep <= 8'hFF;
          s_axis_tlast <= ((b + 8) == PKT_BYTES);
        end
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        b = b + ((b + 8 > PKT_BYTES) ? (PKT_BYTES - b) : 8);
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
      s_axis_tlast  <= 0;
    end
  endtask

  initial begin
    for (npkt = 0; npkt < NPKT; npkt = npkt + 1) begin
      build_pkt(npkt + 1);
      for (ef = 0; ef < PKT_BYTES; ef = ef + 1)
        exp_stream[npkt*PKT_BYTES + ef] = pktbuf[ef];
    end
    // exp_stream holds the full concatenated stream at absolute offsets, so a
    // wrapped read pointer can be resolved as a true byte offset. Do NOT mirror
    // here: indexing must stay absolute.

    // The expected array is complete from here on.
    ready = 1;

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);
    started = 1; // expected array is fully populated by now

    for (npkt = 0; npkt < NPKT; npkt = npkt + 1) begin
      build_pkt(npkt + 1);
      send_built;
    end
    repeat (400000) @(negedge aclk);

    $display("PARITY-TOTAL errs=%0d first_bad=%0d rx_packets=%0d rx_messages=%0d errc=%0d",
             parity_errs, first_bad, dut.rx_packets, dut.rx_messages, dut.error_count);
    $finish;
  end

endmodule
