// tb_starvation: is the spurious rescan caused by the stream pausing between packets?
//
// The real capture parses with err=0; every synthetic case rescan. The capture is streamed
// back-to-back with no gaps - the way a DMA burst arrives. The synthetic benches send a packet,
// wait hundreds of cycles, then send the next.
//
// Case A: two packets, 300 idle cycles between them   (what the earlier probes did)
// Case B: the same two packets, back-to-back          (what a DMA burst looks like)
//
// If B is clean and A is not, the rescan is a starvation artefact.
`timescale 1ns / 1ps

module tb_starvation;

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

  wire [63:0] m_axis_tdata;
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

  // Two 18-byte packets concatenated in one buffer, so they can be sent with no gap.
  reg [7:0] pktbuf [0:35];
  integer   idx;
  integer   k;
  integer   nbytes;
  integer   errA;
  integer   errB;

  task axi_write;
    input [4:0]  addr;
    input [31:0] data;
    begin
      @(negedge aclk);
      s_axi_awaddr = addr; s_axi_wdata = data;
      s_axi_awvalid = 1;   s_axi_wvalid = 1;
      @(posedge aclk);
      while (!(s_axi_awready && s_axi_wready)) @(posedge aclk);
      @(negedge aclk);
      s_axi_awvalid = 0; s_axi_wvalid = 0;
    end
  endtask

  // Send the whole buffer as one burst with no idle cycles between beats.
  task send_burst;
    begin
      k = 0;
      while (k < nbytes) begin
        @(negedge aclk);
        s_axis_tdata  = {pktbuf[k+7], pktbuf[k+6], pktbuf[k+5], pktbuf[k+4],
                         pktbuf[k+3], pktbuf[k+2], pktbuf[k+1], pktbuf[k]};
        if ((k + 8) > nbytes) begin
          case (nbytes - k)
            1: s_axis_tkeep = 8'h01;  2: s_axis_tkeep = 8'h03;
            3: s_axis_tkeep = 8'h07;  4: s_axis_tkeep = 8'h0F;
            5: s_axis_tkeep = 8'h1F;  6: s_axis_tkeep = 8'h3F;
            7: s_axis_tkeep = 8'h7F;  default: s_axis_tkeep = 8'hFF;
          endcase
        end else begin
          s_axis_tkeep = 8'hFF;
        end
        s_axis_tvalid = 1;
        s_axis_tlast  = ((k + 8) >= nbytes);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        k = k + 8;
      end
      @(negedge aclk);
      s_axis_tvalid = 0;
      s_axis_tlast  = 0;
    end
  endtask

  // Send beats from `lo` to `hi` (byte indices), starting at a word boundary.
  task send_range;
    input integer lo;
    input integer hi;
    begin
      k = lo;
      while (k < hi) begin
        @(negedge aclk);
        s_axis_tdata  = {pktbuf[k+7], pktbuf[k+6], pktbuf[k+5], pktbuf[k+4],
                         pktbuf[k+3], pktbuf[k+2], pktbuf[k+1], pktbuf[k]};
        // TKEEP must mark only the bytes that belong to this packet.
        if ((k + 8) > hi) begin
          case (hi - k)
            1: s_axis_tkeep = 8'h01;  2: s_axis_tkeep = 8'h03;
            3: s_axis_tkeep = 8'h07;  4: s_axis_tkeep = 8'h0F;
            5: s_axis_tkeep = 8'h1F;  6: s_axis_tkeep = 8'h3F;
            7: s_axis_tkeep = 8'h7F;  default: s_axis_tkeep = 8'hFF;
          endcase
        end else begin
          s_axis_tkeep = 8'hFF;
        end
        s_axis_tvalid = 1;
        s_axis_tlast  = ((k + 8) >= hi);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        k = k + 8;
      end
      @(negedge aclk);
      s_axis_tvalid = 0;
      s_axis_tlast  = 0;
    end
  endtask

  task build_two;
    begin
      pktbuf[0]=8'h4E; pktbuf[1]=8'h41; pktbuf[2]=8'h53; pktbuf[3]=8'h44;
      pktbuf[4]=8'h41; pktbuf[5]=8'h51; pktbuf[6]=8'h30; pktbuf[7]=8'h31;
      pktbuf[8]=8'h00; pktbuf[9]=8'h01; pktbuf[10]=8'h00; pktbuf[11]=8'h01;
      pktbuf[12]=8'h00; pktbuf[13]=8'h04;
      pktbuf[14]=8'h41; pktbuf[15]=8'h42; pktbuf[16]=8'h43; pktbuf[17]=8'h44;
      pktbuf[18]=8'h4E; pktbuf[19]=8'h41; pktbuf[20]=8'h53; pktbuf[21]=8'h44;
      pktbuf[22]=8'h41; pktbuf[23]=8'h51; pktbuf[24]=8'h30; pktbuf[25]=8'h31;
      pktbuf[26]=8'h00; pktbuf[27]=8'h02; pktbuf[28]=8'h00; pktbuf[29]=8'h01;
      pktbuf[30]=8'h00; pktbuf[31]=8'h04;
      pktbuf[32]=8'h45; pktbuf[33]=8'h46; pktbuf[34]=8'h47; pktbuf[35]=8'h48;
    end
  endtask

  initial begin
    build_two;

    // ---- case A: two packets with a 300-cycle pause between them ----
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    $display("STARVE case A: pause between packets");
    nbytes = 18;
    send_range(0, 18);
    repeat (300) @(negedge aclk);
    send_range(18, 36);
    repeat (600) @(negedge aclk);
    errA = dut.error_count;
    $display("STARVE A: rx_packets=%0d rx_messages=%0d err=%0d gap=%0d",
             dut.rx_packets, dut.rx_messages, errA, dut.gap_count);

    // ---- case B: the same bytes, one burst ----
    axi_write(5'h14, 32'h1);
    repeat (10) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (10) @(negedge aclk);

    $display("STARVE case B: continuous burst");
    nbytes = 36;
    send_burst;
    repeat (900) @(negedge aclk);
    errB = dut.error_count;
    $display("STARVE B: rx_packets=%0d rx_messages=%0d err=%0d gap=%0d",
             dut.rx_packets, dut.rx_messages, errB, dut.gap_count);

    $display("STARVE-SUMMARY pause_err=%0d burst_err=%0d", errA, errB);
    if (errA > 0 && errB == 0)
      $display("STARVE-CONFIRMED: the pause causes the rescan");
    else if (errA == errB)
      $display("STARVE-NOT-THE-CAUSE: both cases behave alike");
    else
      $display("STARVE-SURPRISE: pause_err=%0d burst_err=%0d", errA, errB);

    $finish;
  end

endmodule
