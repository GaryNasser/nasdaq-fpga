// tb_ram_audit: send a known byte stream and audit the ENTIRE RAM against it.
//
// Rather than reasoning about the alignment arithmetic, this compares every
// committed RAM word against the bytes that should be there, and reports the
// first divergence with full context.
`timescale 1ns / 1ps

module tb_ram_audit;

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

  integer i, j, k;
  integer nerr;

  // The exact byte stream we will send: two 50-byte packets back to back.
  reg [7:0] stream [0:99];

  task axi_write(input [4:0] a, input [31:0] d);
    begin
      @(negedge aclk);
      s_axi_awaddr <= a; s_axi_awvalid <= 1;
      s_axi_wdata  <= d; s_axi_wvalid  <= 1;
      while (!(s_axi_awready && s_axi_wready)) @(negedge aclk);
      @(negedge aclk);
      s_axi_awvalid <= 0; s_axi_wvalid <= 0;
      while (!s_axi_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  // Send exactly n bytes from `stream` with an honest TKEEP on the final beat.
  task send_bytes(input integer n);
    integer b;
    reg [63:0] d;
    begin
      b = 0;
      while (b < n) begin
        for (k = 0; k < 8; k = k + 1)
          d[k*8 +: 8] = ((b + k) < n) ? stream[b + k] : 8'h00;
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= d;
        if ((b + 8) > n) begin
          s_axis_tkeep <= (8'hFF >> (8 - (n - b)));
          s_axis_tlast <= 1'b1;
        end else begin
          s_axis_tkeep <= 8'hFF;
          s_axis_tlast <= ((b + 8) == n);
        end
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        b = b + ((b + 8 > n) ? (n - b) : 8);
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
      s_axis_tlast  <= 0;
    end
  endtask

  // Compare the whole RAM against the expected stream.
  task audit(input integer n);
    integer w, lane, pos;
    reg [7:0] got;
    begin
      nerr = 0;
      for (w = 0; w < ((n + 7) / 8); w = w + 1) begin
        $display("AUDIT word[%0d] = %h  (expect %h %h %h %h %h %h %h %h)",
                 w, dut.pkt_ram[w],
                 stream[w*8+0], stream[w*8+1], stream[w*8+2], stream[w*8+3],
                 stream[w*8+4], stream[w*8+5], stream[w*8+6], stream[w*8+7]);
        for (lane = 0; lane < 8; lane = lane + 1) begin
          pos = w * 8 + lane;
          if (pos < n) begin
            got = dut.pkt_ram[w][lane*8 +: 8];
            if (got !== stream[pos]) begin
              $display("  MISMATCH pos=%0d got=%h want=%h", pos, got, stream[pos]);
              nerr = nerr + 1;
            end
          end
        end
      end
      $display("AUDIT-DONE errors=%0d", nerr);
    end
  endtask

  initial begin
    // Packet 1: session + seq=1 + count=1 + len=36 + 36 body bytes
    stream[0]=8'h4E; stream[1]=8'h41; stream[2]=8'h53; stream[3]=8'h44;
    stream[4]=8'h41; stream[5]=8'h51; stream[6]=8'h30; stream[7]=8'h31;
    stream[8]=8'h00; stream[9]=8'h01;
    stream[10]=8'h00; stream[11]=8'h01;
    stream[12]=8'h00; stream[13]=8'h24;
    for (i = 0; i < 36; i = i + 1)
      stream[14+i] = (i == 0) ? 8'h41 : (8'h00 | i[7:0]);
    // Packet 2: same shape, seq=2, body tagged 0xA0
    for (i = 0; i < 50; i = i + 1)
      stream[50+i] = stream[i];
    stream[59] = 8'h02;
    for (i = 0; i < 36; i = i + 1)
      stream[64+i] = (i == 0) ? 8'h45 : (8'hA0 | i[7:0]);

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    // Backpressure held, exactly the failing scenario.
    m_axis_tready <= 0;
    @(negedge aclk);
    send_bytes(100);
    repeat (40) @(negedge aclk);
    $display("STATE acc=%0d wr=%0d rd=%0d err=%0d",
             dut.bytes_accepted, dut.pkt_wr_ptr, dut.pkt_rd_ptr, dut.error_count);
    audit(100);
    $finish;
  end

endmodule
