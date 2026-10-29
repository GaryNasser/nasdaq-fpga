`timescale 1ns / 1ps
module debug_tb;
  reg aclk = 0;
  reg aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg [4:0]  s_axi_awaddr = 0;
  reg        s_axi_awvalid = 0;
  reg [31:0] s_axi_wdata = 0;
  reg [3:0]  s_axi_wstrb = 4'b1111;
  reg        s_axi_wvalid = 0;
  wire       s_axi_wready, s_axi_awready;
  wire [1:0] s_axi_bresp;
  wire       s_axi_bvalid;
  reg        s_axi_bready = 1;
  reg [4:0]  s_axi_araddr = 0;
  reg        s_axi_arvalid = 0;
  wire       s_axi_arready;
  wire [31:0] s_axi_rdata;
  wire [1:0] s_axi_rresp;
  wire        s_axi_rvalid;
  reg         s_axi_rready = 1;

  reg [63:0] s_axis_tdata = 0;
  reg [7:0]  s_axis_tkeep = 8'hFF;
  reg        s_axis_tvalid = 0;
  wire       s_axis_tready;
  reg        s_axis_tlast = 0;

  wire [7:0]  m_axis_tdata;
  wire        m_axis_tvalid;
  reg         m_axis_tready = 1;
  wire        m_axis_tlast;

  mold64_reasm #(.SESSION(64'h4E41534441513031), .FIFO_AW(12)) dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(s_axi_awaddr), .s_axi_awprot(0),
    .s_axi_awvalid(s_axi_awvalid), .s_axi_awready(s_axi_awready),
    .s_axi_wdata(s_axi_wdata), .s_axi_wstrb(s_axi_wstrb),
    .s_axi_wvalid(s_axi_wvalid), .s_axi_wready(s_axi_wready),
    .s_axi_bresp(s_axi_bresp), .s_axi_bvalid(s_axi_bvalid), .s_axi_bready(s_axi_bready),
    .s_axi_araddr(s_axi_araddr), .s_axi_arprot(0),
    .s_axi_arvalid(s_axi_arvalid), .s_axi_arready(s_axi_arready),
    .s_axi_rdata(s_axi_rdata), .s_axi_rresp(s_axi_rresp),
    .s_axi_rvalid(s_axi_rvalid), .s_axi_rready(s_axi_rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .m_axis_tdata(m_axis_tdata), .m_axis_tkeep(),
    .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
    .m_axis_tlast(m_axis_tlast)
  );

  task s_send(input [63:0] d, input [7:0] tk, input last);
    begin : hs
      reg done;
      done = 0;
      @(negedge aclk);
      s_axis_tdata  <= d;
      s_axis_tkeep  <= tk;
      s_axis_tvalid <= 1;
      s_axis_tlast  <= last;
      while (!done) begin
        @(posedge aclk);
        if (s_axis_tvalid && s_axis_tready) begin
          done = 1;
          s_axis_tvalid <= 0;
          s_axis_tlast  <= 0;
        end
      end
      @(negedge aclk);
    end
  endtask

  integer cyc = 0;
  always @(posedge aclk) begin
    if (aresetn) begin
      cyc = cyc + 1;
      if (cyc <= 120)
        $display("cyc=%0d state=%0d rx_done=%b en=%b bv=%b bvr=%b bvr2=%b rdptr=%0d wrptr=%0d m_valid=%b m_byte=%02h",
          cyc, dut.state, dut.pkt_rx_done, dut.enable,
          dut.byte_valid, dut.byte_valid_reg, dut.byte_valid_reg2,
          dut.pkt_rd_ptr, dut.pkt_wr_ptr,
          m_axis_tvalid, m_axis_tdata);
    end
  end

  initial begin
    repeat(4) @(negedge aclk);
    aresetn = 1;
    repeat(2) @(negedge aclk);

    // Enable
    @(negedge aclk);
    s_axi_awaddr = 5'h18;
    s_axi_awvalid = 1;
    s_axi_wdata = 32'd1;
    s_axi_wvalid = 1;
    while (!(s_axi_awvalid && s_axi_awready && s_axi_wvalid && s_axi_wready))
      @(posedge aclk);
    s_axi_awvalid = 0;
    s_axi_wvalid = 0;
    $display("=== ENABLED ===");

    // Send 50-byte packet: session(8)+seq(2)+count(2)+msglen(2)+body(36)
    s_send({8'h31,8'h30,8'h51,8'h41,8'h44,8'h53,8'h41,8'h4E}, 8'hFF, 0); // session
    $display("BEAT0 done wrptr=%0d", dut.pkt_wr_ptr);
    s_send({8'h01,8'h00,8'h01,8'h00,8'h00,8'h00,8'h00,8'h00}, 8'hFF, 0); // seq+count
    $display("BEAT1 done wrptr=%0d", dut.pkt_wr_ptr);
    s_send({8'h00,8'h41,8'h01,8'h02,8'h03,8'h04,8'h24,8'h00}, 8'hFF, 0); // msglen+body[0..5]
    $display("BEAT2 done wrptr=%0d", dut.pkt_wr_ptr);
    s_send({8'h0A,8'h09,8'h08,8'h07,8'h06,8'h05,8'h04,8'h03}, 8'hFF, 0);
    s_send({8'h12,8'h11,8'h10,8'h0F,8'h0E,8'h0D,8'h0C,8'h0B}, 8'hFF, 0);
    s_send({8'h1A,8'h19,8'h18,8'h17,8'h16,8'h15,8'h14,8'h13}, 8'hFF, 0);
    s_send({8'h00,8'h00,8'h00,8'h00,8'h1E,8'h1D,8'h1C,8'h1B}, 8'h1F, 1); // last
    $display("=== PKT_SENT wrptr=%0d rx_done=%b ===", dut.pkt_wr_ptr, dut.pkt_rx_done);

    repeat(200) @(posedge aclk);
    $display("=== DONE state=%0d m_valid=%b ===", dut.state, m_axis_tvalid);
    $finish;
  end
endmodule
